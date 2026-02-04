"""Read model projector runner using eventsourcing standard pattern with mixed persistence."""

from __future__ import annotations

import signal

import structlog
from eventsourcing.application import Application
from eventsourcing.persistence import IntegrityError
from eventsourcing.projection import ApplicationSubscription

from infrastructure.di.container import create_container
from infrastructure.event_projectors.event_projector import EventProjector
from infrastructure.event_projectors.policy_dispatcher import PolicyDispatcher
from infrastructure.logging import setup_logging

setup_logging()

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
    policy_dispatcher = container[PolicyDispatcher]

    def handle_signal(signum: int, _frame: object) -> None:
        logger.info("read_model_signal_received", signum=signum)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    all_topics = list({*event_projector.topics, *policy_dispatcher.topics})
    logger.info("read_model_projector_started", topics=len(all_topics))

    try:
        # Get last processed position from tracking collection
        application_name = app.name
        materializer = event_projector.materializer
        max_tracking_id = materializer.max_tracking_id(application_name)
        logger.info("read_model_resuming", last_position=max_tracking_id)

        # Subscribe and process events using standard pattern
        logger.info("read_model_creating_subscription", topics=len(all_topics))
        # Convert event types to their fully qualified names for ApplicationSubscription
        # For nested event classes, we need to use __qualname__ which includes the parent class
        topic_names = [f"{evt.__module__}:{evt.__qualname__}" for evt in all_topics]
        logger.info("read_model_subscription_topics", topics=topic_names)
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
                    try:
                        event_count += 1
                        event_type = type(domain_event).__name__
                        logger.info(
                            "read_model_event_received",
                            event_num=event_count,
                            event_type=event_type,
                            tracking_id=tracking.notification_id,
                        )
                        # Use the event projector and policy dispatcher to route the event
                        event_projector.process_event(domain_event, tracking)
                        policy_dispatcher.process_event(domain_event, tracking)
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
