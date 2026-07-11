from application.use_cases.compound_profile_use_case import GetCompoundProfileUseCase
from infrastructure.di.container import create_container


def test_container_resolves_compound_profile_use_case():
    container = create_container()
    assert isinstance(container[GetCompoundProfileUseCase], GetCompoundProfileUseCase)


def test_compound_profile_route_registered():
    from interfaces.api.main import app

    paths = {r.path for r in app.routes}
    assert "/compounds/{name}/profile" in paths
