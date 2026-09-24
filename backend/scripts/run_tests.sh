#!/bin/bash
cd /home/techpark-9/Time_Table_Scheduler/backend
source venv/bin/activate
export PYTHONPATH=.
pip install pytest pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
