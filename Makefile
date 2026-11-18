test:
	cd backend && python3 -m pytest -q
rubric:
	python3 -I scripts/build_rubric_schema.py
ext-test:
	cd extension && node --test tests/*.test.js
doctor:
	cd backend && python3 scripts/doctor.py
eval:
	cd backend && python3 scripts/eval_golden.py
seed:
	cd backend && python3 scripts/seed_demo.py
zip:
	sh extension/build_zip.sh
preview:
	python3 scripts/make_preview.py
ext-e2e:
	cd extension && python3 tests/e2e_content.py
client:
	@echo "usage: python3 scripts/make_client.py --url http://SERVER:8000 --token TOKEN"
