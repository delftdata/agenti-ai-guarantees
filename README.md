# agenti-ai-guarantees

This repo investigates performance differences between sequential and distributed agentic workflows in LangGraph.

## Setup

1. Create virtual environment: `python3 -m venv agentic-ai-guarantees`
2. Activate virtual environment: `source agentic-ai-guarantees/bin/activate`
3. Upgrade pip: `pip3 install --upgrade pip`
4. Install packages: `pip3 install -r requirements.txt`
5. Set the Google API key: `export GOOGLE_API_KEY='<YOUR API KEY HERE>'`
6. Uncomment the `profile_run` calls in `profile_plans.py`
7. Run the script: `python3 profile_plans.py`