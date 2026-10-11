"""FastAPI application factory; one process owns each local demo database."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response

from app.config import Settings
from app.providers.base import ModelProvider, SearchProvider
from app.providers.deepseek import DeepSeekModelProvider
from app.providers.openai_compat import OpenAICompatModelProvider
from app.providers.profiles import parse_council_model_map, PROFILE_MODELS, PROFILE_URLS
from app.providers.tavily import TavilySearchProvider
from app.repository import DecisionRepository
from app.markdown_export import render_decision_markdown
from app.schemas import DecisionCreate, ReviewRequest, ObjectionLabelsRequest, InvalidInput, OutcomeRequest, RetrospectiveCreate
from app.workflow import WorkflowEngine


def _has_secret(value) -> bool:
    return value is not None and bool(value.get_secret_value().strip())


def create_app(
    database_path: Path | None = None,
    *,
    settings: Settings | None = None,
    model_provider: ModelProvider | None = None,
    search_provider: SearchProvider | None = None,
) -> FastAPI:
    settings = settings or Settings()
    repository = DecisionRepository(database_path if database_path is not None else settings.database_url)
    model_key = settings.deepseek_api_key if settings.model_provider == 'deepseek' else settings.openai_compat_api_key
    council_map = parse_council_model_map(settings.council_model_map)
    missing_profiles = {profile for profile, _ in council_map.values()
                        if not _has_secret(getattr(settings, profile + '_api_key'))}
    if not _has_secret(model_key):
        missing_profiles.add(settings.model_provider)
    live_model_configured = not missing_profiles
    live_search_configured = _has_secret(settings.tavily_api_key)
    live_requested = settings.app_mode == 'live' and settings.enable_live_workflow

    constructed_model = model_provider
    constructed_search = search_provider
    council_providers = {}
    if live_requested and live_model_configured and constructed_model is None:
        if settings.model_provider == 'openai_compat':
            constructed_model = OpenAICompatModelProvider(
                api_key=model_key, base_url=settings.openai_compat_base_url,
                model=settings.openai_compat_model, timeout_seconds=settings.deepseek_timeout_seconds,
                max_output_tokens=settings.deepseek_max_output_tokens, recorder=repository,
            )
        else:
            constructed_model = DeepSeekModelProvider(
                api_key=model_key, model=settings.deepseek_model,
                timeout_seconds=settings.deepseek_timeout_seconds,
                max_output_tokens=settings.deepseek_max_output_tokens, recorder=repository,
            )
    if live_requested and live_model_configured:
        cache = {}
        for role, (profile, override) in council_map.items():
            model = override or (settings.deepseek_model if profile == 'deepseek' else PROFILE_MODELS[profile])
            if profile == settings.model_provider and model == settings.deepseek_model:
                council_providers[role] = constructed_model
                continue
            identity = (profile, model)
            if identity not in cache:
                options = dict(api_key=getattr(settings, profile + '_api_key'), model=model,
                               timeout_seconds=settings.deepseek_timeout_seconds,
                               max_output_tokens=settings.deepseek_max_output_tokens, recorder=repository)
                cache[identity] = (DeepSeekModelProvider(**options) if profile == 'deepseek' else
                                   OpenAICompatModelProvider(**options, base_url=PROFILE_URLS[profile], profile=profile))
            council_providers[role] = cache[identity]
    if live_requested and live_search_configured and constructed_search is None:
        constructed_search = TavilySearchProvider(
            api_key=settings.tavily_api_key,
            timeout_seconds=settings.tavily_timeout_seconds,
            trusted_domains=settings.tavily_trusted_domains,
            blocked_domains=settings.tavily_blocked_domains,
            recorder=repository,
        )

    live_available = bool(
        live_requested
        and live_model_configured
        and live_search_configured
        and constructed_model is not None
        and constructed_search is not None
    )
    workflow = WorkflowEngine(
        repository,
        model_provider=constructed_model if live_available else None,
        search_provider=constructed_search if live_available else None,
        mode=settings.app_mode,
        council_providers=council_providers if live_available else None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        workflow.recover_interrupted()
        yield
        closed: set[int] = set()
        for provider in (constructed_model, constructed_search, *council_providers.values()):
            close = getattr(provider, 'close', None)
            if provider is not None and id(provider) not in closed and callable(close):
                close()
                closed.add(id(provider))
        repository._engine.dispose()

    app = FastAPI(title='VeriPlan API', lifespan=lifespan)
    app.state.settings = settings
    app.state.repository = repository
    app.state.workflow = workflow
    app.state.live_available = live_available

    def require_mutations_available():
        if settings.app_mode == 'demo':
            return
        if not live_available:
            raise HTTPException(
                status_code=503,
                detail=('Live workflow is locked or incompletely configured.'
                        + (' Missing profiles: ' + ', '.join(sorted(missing_profiles | ({'tavily'} if not live_search_configured else set())))
                           if missing_profiles or not live_search_configured else '')),
            )

    def invoke(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except KeyError as error:
            raise HTTPException(status_code=404, detail='Decision not found') from error
        except InvalidInput as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get('/api/health')
    def health():
        from sqlalchemy import text
        with repository._engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {
            'status': 'ok' if settings.app_mode == 'demo' or live_available else 'unavailable',
            'mode': settings.app_mode,
            'database': 'ok',
            'live_workflow_enabled': settings.enable_live_workflow,
            'live_model_configured': live_model_configured,
            'live_model_adapter_available': True,
            'live_search_configured': live_search_configured,
            'live_search_adapter_available': True,
            'live_search_available': bool(
                live_requested
                and live_search_configured
                and constructed_search is not None
            ),
            'live_available': live_available,
        }

    @app.get('/api/decisions')
    def list_decisions():
        return repository.list()

    @app.get('/api/decisions/{decision_id}')
    def get_decision(decision_id: str):
        return invoke(repository.get, decision_id)

    @app.get('/api/decisions/{decision_id}/export.md')
    def export_decision_markdown(decision_id: str):
        snapshot = invoke(repository.get, decision_id)
        if snapshot.memo is None:
            raise HTTPException(status_code=409, detail='Decision report is not ready')
        return Response(
            content=render_decision_markdown(snapshot),
            media_type='text/markdown; charset=utf-8',
            headers={
                'Content-Disposition': (
                    f'attachment; filename="veriplan-{snapshot.id}.md"'
                )
            },
        )

    @app.post('/api/decisions', status_code=201)
    def create_decision(payload: DecisionCreate):
        require_mutations_available()
        return repository.create(payload, mode=settings.app_mode)

    @app.post('/api/decisions/{decision_id}/run', status_code=202)
    def run_decision(decision_id: str, background_tasks: BackgroundTasks):
        require_mutations_available()
        snapshot = invoke(workflow.prepare_run, decision_id)
        background_tasks.add_task(workflow.run_prepared, decision_id)
        return snapshot

    @app.post('/api/decisions/{decision_id}/retry', status_code=202)
    def retry_decision(decision_id: str, background_tasks: BackgroundTasks):
        require_mutations_available()
        snapshot = invoke(workflow.prepare_run, decision_id, retry=True)
        background_tasks.add_task(workflow.run_prepared, decision_id)
        return snapshot

    @app.post('/api/decisions/{decision_id}/confirm')
    def confirm_decision(decision_id: str):
        require_mutations_available()
        invoke(workflow.confirm_clarification, decision_id)
        return repository.get(decision_id)

    @app.post('/api/decisions/{decision_id}/review')
    def review_decision(decision_id: str, payload: ReviewRequest):
        require_mutations_available()
        invoke(
            workflow.apply_review,
            decision_id,
            action=payload.action,
            note=payload.note,
        )
        return repository.get(decision_id)

    @app.post('/api/decisions/{decision_id}/objection-labels')
    def label_objections(decision_id: str, payload: ObjectionLabelsRequest):
        require_mutations_available()
        invoke(repository.save_objection_labels, decision_id, payload.labels, mode=settings.app_mode)
        return repository.get(decision_id)

    @app.post('/api/decisions/{decision_id}/outcomes')
    def record_outcomes(decision_id: str, payload: OutcomeRequest):
        require_mutations_available()
        invoke(repository.save_outcome, decision_id, payload, mode=settings.app_mode)
        return repository.get(decision_id)

    @app.post('/api/retrospectives', status_code=201)
    def create_retrospective(payload: RetrospectiveCreate):
        require_mutations_available()
        return invoke(repository.create_retrospective, payload, mode=settings.app_mode)

    @app.get('/api/calibration')
    def get_calibration():
        from app.calibration import calibration_profile
        return calibration_profile(repository.list(), mode=settings.app_mode)

    return app


app = create_app()
