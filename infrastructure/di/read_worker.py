"""Read model projector runner using eventsourcing standard pattern with mixed persistence."""

from __future__ import annotations

import signal

import structlog
from eventsourcing.application import Application
from eventsourcing.persistence import IntegrityError
from eventsourcing.projection import ApplicationSubscription

from infrastructure.di.container import create_container
from infrastructure.event_projectors.event_projector import EventProjector

logger = structlog.get_logger()


def run() -> None:
    """Run the MongoDB read model projector.

    Uses mixed persistence:
    - Event store: KurrentDB
    - Read models: MongoDB

    This follows the eventsourcing Projection pattern but handles the view
    construction manually since ProjectorRunner expects single persistence.
    """
    # Use DI container to get properly configured instances
    container = create_container()
    app = container[Application]
    event_projector = container[EventProjector]

    stop_requested = False

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        logger.info("read_model_signal_received", signum=signum)
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("read_model_projector_started", topics=len(event_projector.topics))

    try:
        # Get last processed position from tracking collection
        application_name = app.name
        materializer = event_projector.materializer
        max_tracking_id = materializer.max_tracking_id(application_name)
        logger.info("read_model_resuming", last_position=max_tracking_id)

        # Subscribe and process events using standard pattern
        logger.info("read_model_creating_subscription", topics=len(event_projector.topics))
        # Convert event types to their fully qualified names for ApplicationSubscription
        topic_names = [f"{evt.__module__}:{evt.__name__}" for evt in event_projector.topics]
        subscription = ApplicationSubscription(
            app,
            gt=max_tracking_id,
            topics=topic_names,
        )
        logger.info("read_model_subscription_created")

        event_count = 0
        with subscription:
            try:
                for domain_event, tracking in subscription:  # This is where events are received
                    if stop_requested:
                        logger.info("read_model_stop_requested")
                        break

                    try:
                        event_count += 1
                        event_type = type(domain_event).__name__
                        logger.info(
                            "read_model_event_received",
                            event_num=event_count,
                            event_type=event_type,
                            tracking_id=tracking.notification_id,
                        )
                        # Use the event projector to route the event
                        event_projector.process_event(domain_event, tracking)
                        logger.info(
                            "read_model_event_processed",
                            event_type=event_type,
                            tracking_id=tracking.notification_id,
                        )
                    except IntegrityError:
                        # Event already processed - skip it
                        logger.info(
                            "read_model_event_already_processed",
                            tracking_id=tracking.notification_id,
                        )
                    except Exception:
                        logger.exception(
                            "read_model_event_processing_error",
                            event_type=type(domain_event).__name__,
                            tracking_id=tracking.notification_id,
                        )
                        # Don't re-raise, just log and continue
                        logger.warning("read_model_continuing_after_error")

            except StopIteration:
                logger.info("read_model_subscription_stopped")
            finally:
                logger.info("read_model_subscription_closed", events_processed=event_count)

    except KeyboardInterrupt:
        logger.info("read_model_interrupted")
    except Exception:
        logger.exception("read_model_projector_error")
        raise
    finally:
        logger.info("read_model_projector_stopped")


if __name__ == "__main__":
    run()
