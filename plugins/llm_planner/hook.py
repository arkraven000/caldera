"""llm_planner plugin entry point.

Registers a YAML planner doc pointing at plugins.llm_planner.app.llm_planner.LogicalPlanner
so the standard planner-selection UI / API picks it up alongside `atomic` / `batch`.
"""

import logging
import os

from app.objects.c_planner import Planner

name = 'llm_planner'
description = 'LLM-driven planner using Anthropic Claude. Defaults to dry-run; live execution opt-in via planner params.'
address = None
access = None


async def enable(services):
    data_svc = services.get('data_svc')
    planner_yml = os.path.join('plugins', 'llm_planner', 'data', 'planners', '7c2b0e10-llm-planner.yml')
    if not os.path.exists(planner_yml):
        logging.warning('llm_planner: planner YAML not found at %s', planner_yml)
        return
    try:
        await data_svc.load_yaml_file(Planner, planner_yml)
        logging.info('llm_planner: registered planner from %s', planner_yml)
    except Exception as exc:
        logging.exception('llm_planner: failed to register planner: %s', exc)
