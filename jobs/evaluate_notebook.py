# Databricks notebook source
# Runs the packaged real evaluation suite as a Databricks Workflow task.
import json
import os
import sys

dbutils.widgets.text('deployment_config', '{}')  # noqa: F821
dbutils.widgets.text('judge_model', '')  # noqa: F821
configuration = json.loads(dbutils.widgets.get('deployment_config'))  # noqa: F821
# Configuration is job-owner administered. Credentials use the job's native identity.
os.environ.update({key: str(value) for key, value in configuration.items()})
if os.environ.get('LAKEBASE_ENDPOINT'):
    os.environ['LAKEBASE_AUTOSCALING_ENDPOINT'] = os.environ['LAKEBASE_ENDPOINT']
from evaluations.run import main
sys.argv = ['evaluate', '--judge-model', dbutils.widgets.get('judge_model')]  # noqa: F821
main()
