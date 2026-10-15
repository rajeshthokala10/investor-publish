# Bengaluru Property Review — one application, one set of commands.
PY ?= python3
CLI = $(PY) -m harness.cli

.PHONY: help batch daily magazine site serve web-install web-stop schedule status test pause resume email email-preview

help:            ## list commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-13s %s\n", $$1, $$2}'
batch:           ## full batch: daily research, monthly magazine, weekly, metrics, website data
	$(CLI) batch
daily:           ## daily 72-hour research + brief only
	$(CLI) run
magazine:        ## build this month's magazine (research, verify, write, render)
	$(CLI) magazine
site:            ## refresh dashboard metrics and website data from existing reports
	$(CLI) batch --steps metrics,site
serve:           ## run the website in the foreground on http://127.0.0.1:8787
	$(CLI) serve
web-install:     ## run the website as a background service (auto-restart, starts at login)
	$(CLI) web install
web-stop:        ## stop and remove the website service
	$(CLI) web uninstall
schedule:        ## install the 06:00 IST batch schedule
	$(CLI) schedule install
status:          ## scheduler, website service, last runs
	$(CLI) status; $(CLI) web status
pause:           ## pause scheduled runs
	$(CLI) pause
resume:          ## resume scheduled runs
	$(CLI) resume
email:           ## send today's "Bangalore RealEstate Delta" email (dry run until SMTP is set in .env)
	$(CLI) email
email-preview:   ## write today's email to data/app/outbox/ without sending
	$(CLI) email --dry-run
test:            ## run the test suite
	$(PY) -m pytest -q tests
