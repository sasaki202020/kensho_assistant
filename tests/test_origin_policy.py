import pytest


@pytest.mark.parametrize('url', [
    'https://x.com', 'https://a.twitter.com', 'https://instagram.com',
    'https://facebook.com', 'https://line.me', 'https://tiktok.com',
    'https://youtube.com', 'https://accounts.google.com', 'https://apple.com',
    'https://amazon.co.jp', 'https://amazon.com', 'https://rakuten.co.jp',
    'https://paypal.com', 'https://paypay.ne.jp', 'https://login.yahoo.co.jp',
    'https://a.login.yahoo.co.jp', 'https://signin.campaign.test',
    'https://myaccount.campaign.test', 'https://auth.campaign.test',
    'https://payment.campaign.test', 'http://campaign.test',
    'http://127.0.0.1:8123', 'https://user:secret@campaign.test',
    'https://campaign.test:8443', 'https://campaign.test:0',
])
def test_policy_rejects_unsafe_origins(url):
    from kensho_assistant.app.origin_policy import is_origin_allowed
    allowed, reason = is_origin_allowed(url)
    assert allowed is False
    assert reason


def test_normalization_and_explicit_fixture_flag():
    from kensho_assistant.app.origin_policy import normalize_origin, is_origin_allowed
    assert normalize_origin('https://Campaign.test:443/form') == 'https://campaign.test'
    assert is_origin_allowed('https://campaign.test') == (True, '')
    assert is_origin_allowed('https://yahoo.co.jp') == (True, '')
    assert is_origin_allowed('http://localhost:8123', allow_loopback_http=True) == (True, '')
    assert is_origin_allowed('http://campaign.test', allow_loopback_http=True)[0] is False


def test_candidate_approval_required_before_browser_launch():
    from kensho_assistant.app.browser_manager import validate_dedicated_target_url
    url = 'https://campaign.test/form'
    assert validate_dedicated_target_url(url, approved_candidate_origin='https://campaign.test') == url
    for candidate in (None, 'https://other.test'):
        with pytest.raises(ValueError, match='dedicated_target_not_allowed'):
            validate_dedicated_target_url(url, approved_candidate_origin=candidate)
    with pytest.raises(ValueError, match='dedicated_target_not_allowed'):
        validate_dedicated_target_url('https://x.com/form', approved_candidate_origin='https://x.com')


def test_denylist_config_can_add_but_cannot_remove_defaults(tmp_path, monkeypatch):
    import json
    from kensho_assistant.app import paths
    from kensho_assistant.app.origin_policy import is_origin_allowed
    monkeypatch.setattr(paths, 'CONFIG_DIR', tmp_path)
    config = tmp_path / 'origin_denylist.json'
    config.write_text(json.dumps({'schema_version': 1, 'domains': ['custom.test']}))
    assert is_origin_allowed('https://custom.test')[0] is False
    assert is_origin_allowed('https://sub.custom.test')[0] is False
    assert is_origin_allowed('https://x.com')[0] is False
    assert is_origin_allowed('https://campaign.test')[0] is True
    config.write_text('{invalid')
    assert is_origin_allowed('https://campaign.test')[0] is False


@pytest.mark.parametrize('change', [
    {'approved_by_user': 'false'}, {'queue_status': 'QUEUED'},
    {'resolved_entry_url': ''}, {'terms_automation_restricted': 'true'},
    {'deadline': '2000-01-01'},
])
def test_candidate_origin_requires_saved_user_approval(change):
    from kensho_assistant.app.assisted_session import approved_candidate_origin
    row = {'approved_by_user': 'true', 'queue_status': 'APPROVED',
           'resolved_entry_url': 'https://campaign.test/form'}
    assert approved_candidate_origin(row) == 'https://campaign.test'
    with pytest.raises(ValueError, match='dedicated_target_not_allowed'):
        approved_candidate_origin({**row, **change})


def test_denied_candidate_stops_before_playwright(tmp_path, monkeypatch):
    from kensho_assistant.app import assisted_session as session
    monkeypatch.setattr(session, 'ASSISTED_SESSION_STATE_JSON', tmp_path / 'session.json')
    monkeypatch.setattr(session, 'approved_queue_rows', lambda: [
        {'campaign_id': 'denied-fixture', 'approved_by_user': 'true', 'queue_status': 'APPROVED',
         'resolved_entry_url': 'https://x.com/form'}])
    monkeypatch.setattr(session, 'sync_playwright', lambda: pytest.fail('browser must not start'))
    result = session.run_assisted_application_session(limit=1)
    assert result['status'] == 'stopped'
    assert result['submitted_count_auto'] == 0


def test_activation_readback_failure_closes_without_navigation(monkeypatch):
    from kensho_assistant.app import browser_manager as manager
    calls = []
    context = object()
    monkeypatch.setattr(manager, 'live_extension_worker', lambda *a, **k: object())
    monkeypatch.setattr(manager, 'evaluate_worker', lambda worker, expression, *a, **k:
        True if expression == '() => dedicatedRuntimeOriginMode()' else
        {'originPattern': 'https://other.test/*', 'sessionId': 'session'})
    monkeypatch.setattr(manager, 'close_browser_safely', lambda c: calls.append(c))
    with pytest.raises(RuntimeError, match='active_origin_unverified'):
        manager.set_active_origin(context, 'https://campaign.test', 'session')
    assert calls == [context]
