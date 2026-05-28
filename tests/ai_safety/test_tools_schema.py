import json

from app.ai_safety import CALDERA_TOOL_SPECS, CHOOSE_NEXT_LINK_TOOL


def test_choose_next_link_tool_is_json_serializable():
    encoded = json.dumps(CHOOSE_NEXT_LINK_TOOL)
    decoded = json.loads(encoded)
    assert decoded['name'] == 'choose_next_link'
    schema = decoded['input_schema']
    assert schema['type'] == 'object'
    assert 'ability_id' in schema['required']
    assert 'reasoning' in schema['required']
    assert 'confidence' in schema['required']


def test_caldera_tool_specs_have_unique_names():
    names = [spec['name'] for spec in CALDERA_TOOL_SPECS]
    assert len(names) == len(set(names))


def test_caldera_tool_specs_minimum_set():
    names = {spec['name'] for spec in CALDERA_TOOL_SPECS}
    must_have = {'list_abilities', 'get_operation', 'list_agents', 'get_facts',
                 'propose_link', 'execute_link', 'stop_operation'}
    assert must_have.issubset(names)


def test_all_tools_have_input_schema():
    for spec in CALDERA_TOOL_SPECS:
        assert 'name' in spec
        assert 'description' in spec
        assert 'input_schema' in spec
        assert spec['input_schema']['type'] == 'object'
