.PHONY: install test audit-sample audit-full all-sample

install:
	pip install -r requirements.txt
	pip install -e .

test:
	pytest tests -q

audit-sample:
	python -m rainfall.cli all --sample

audit-full:
	python -m rainfall.cli ingest
	python -m rainfall.cli audit

all-sample: audit-sample
