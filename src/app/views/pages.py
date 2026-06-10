"""Content pages backed by Google Doc tabs."""
from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
import mistune

from ..services.content_cache import ContentCache

pages_bp = Blueprint('pages', __name__)


def _get_cache() -> ContentCache:
    cache = current_app.extensions.get('content_cache')
    if not isinstance(cache, ContentCache):
        raise RuntimeError('ContentCache is not configured.')
    return cache


@pages_bp.route('/')
def index():  # type: ignore[no-untyped-def]
    tabs = _get_cache().get_tabs(request.host_url)
    if not tabs:
        abort(503)
    return redirect(url_for('pages.page', slug=tabs[0].slug))


@pages_bp.route('/<slug>')
def page(slug: str):  # type: ignore[no-untyped-def]
    tabs = _get_cache().get_tabs(request.host_url)
    tab = next((t for t in tabs if t.slug == slug), None)
    if tab is None:
        abort(404)
    content_html = mistune.html(tab.content)
    return render_template('page.html', tab=tab, content_html=content_html)
