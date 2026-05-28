"""Tests for app.ai_safety.catalog — the compact projections sent to the LLM.

These projections are what the model actually sees. If a field changes shape or a
sentinel-None leaks through, the model may hallucinate inputs. Long descriptions
must be truncated so they don't crowd out the rest of the prompt context.
"""

from types import SimpleNamespace

import pytest

from app.ai_safety.catalog import (
    build_ability_catalog,
    compact_ability,
    compact_agent,
    compact_fact,
    compact_link,
)


class _Executor:
    def __init__(self, platform):
        self.platform = platform


def _ability(ability_id='a1', tactic='discovery', technique_id='T1083',
             name='probe', description='', executors=()):
    return SimpleNamespace(
        ability_id=ability_id, tactic=tactic, technique_id=technique_id,
        name=name, technique_name='Probe Technique',
        description=description, executors=list(executors),
    )


def test_compact_ability_includes_platforms_from_executors():
    a = _ability(executors=[_Executor('linux'), _Executor('darwin'), _Executor('linux')])
    out = compact_ability(a)
    assert out['ability_id'] == 'a1'
    assert out['platforms'] == ['darwin', 'linux']  # sorted, deduped


def test_compact_ability_truncates_long_description():
    a = _ability(description='x' * 1000)
    out = compact_ability(a)
    assert len(out['description']) == 300


def test_compact_ability_handles_missing_attrs_gracefully():
    minimal = SimpleNamespace(ability_id='only-id')
    out = compact_ability(minimal)
    assert out['ability_id'] == 'only-id'
    assert out['name'] is None
    assert out['platforms'] == []
    assert out['description'] == ''


def test_compact_link_pulls_ability_fields_through():
    link = SimpleNamespace(
        id='link-1', paw='paw-1', ability=_ability(name='ls'),
        score=42, executor=_Executor('linux'),
    )
    out = compact_link(link)
    assert out['link_id'] == 'link-1'
    assert out['paw'] == 'paw-1'
    assert out['ability_id'] == 'a1'
    assert out['ability_name'] == 'ls'
    assert out['score'] == 42
    assert out['platform'] == 'linux'


def test_compact_link_tolerates_missing_ability():
    link = SimpleNamespace(id='l1', paw='p1', ability=None, score=0, executor=None)
    out = compact_link(link)
    assert out['link_id'] == 'l1'
    assert out['ability_id'] is None
    assert out['platform'] is None


def test_compact_fact_typical():
    fact = SimpleNamespace(trait='host.user.name', value='alice', score=1, source='op1')
    out = compact_fact(fact)
    assert out == {'trait': 'host.user.name', 'value': 'alice', 'score': 1, 'source': 'op1'}


def test_compact_agent_stringifies_last_seen():
    from datetime import datetime
    a = SimpleNamespace(paw='p1', host='h1', platform='linux', username='u',
                        privilege='User', trusted=True,
                        last_seen=datetime(2026, 1, 1, 12, 0, 0))
    out = compact_agent(a)
    assert out['paw'] == 'p1'
    assert '2026' in out['last_seen']


@pytest.mark.asyncio
async def test_build_ability_catalog_sorted_and_filtered():
    abilities = [
        _ability(ability_id='b', tactic='discovery', name='zzz'),
        _ability(ability_id='a', tactic='discovery', name='aaa'),
        _ability(ability_id='c', tactic='impact', name='mmm'),
    ]

    class FakeDataSvc:
        async def locate(self, name):
            assert name == 'abilities'
            return abilities

    rows = await build_ability_catalog(FakeDataSvc(), tactic='discovery')
    assert [r['ability_id'] for r in rows] == ['a', 'b']  # sorted by (tactic, name)


@pytest.mark.asyncio
async def test_build_ability_catalog_filters_by_technique_id():
    abilities = [
        _ability(ability_id='a', technique_id='T1'),
        _ability(ability_id='b', technique_id='T2'),
    ]

    class FakeDataSvc:
        async def locate(self, name):
            return abilities

    rows = await build_ability_catalog(FakeDataSvc(), technique_id='T2')
    assert len(rows) == 1
    assert rows[0]['ability_id'] == 'b'


@pytest.mark.asyncio
async def test_build_ability_catalog_tactic_filter_case_insensitive():
    abilities = [_ability(ability_id='a', tactic='Discovery')]

    class FakeDataSvc:
        async def locate(self, name):
            return abilities

    rows = await build_ability_catalog(FakeDataSvc(), tactic='discovery')
    assert len(rows) == 1
