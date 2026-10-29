# Mac host entry points. Scripts live under src/host/.
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ACCESS_TOKEN := $(ROOT)/src/host/access-token/access-token.sh
DAILY := $(ROOT)/src/host/daily/daily.sh
INSTALL_DAILY := $(ROOT)/src/host/install-daily-agent/install-daily-agent.sh

.DEFAULT_GOAL := help

.PHONY: help login inject one-shot daily install-daily-agent host-check

help:
	@printf '%s\n' \
		'Host targets (Mac):' \
		'  make login ALIAS=email1|email2' \
		'  make inject CONTAINER=<name>' \
		'  make one-shot' \
		'  make daily' \
		'  make install-daily-agent' \
		'  make host-check'

login:
ifndef ALIAS
	$(error usage: make login ALIAS=email1|email2)
endif
	"$(ACCESS_TOKEN)" login "$(ALIAS)"

inject:
ifndef CONTAINER
	$(error usage: make inject CONTAINER=<docker-container>)
endif
	"$(ACCESS_TOKEN)" inject "$(CONTAINER)"

one-shot:
	"$(ACCESS_TOKEN)" one-shot

daily:
	"$(DAILY)"

install-daily-agent:
	"$(INSTALL_DAILY)"

host-check:
	shellcheck "$(ROOT)"/src/host/*/*.sh
	@for test in "$(ROOT)"/src/host/*/*.test.sh; do bash "$$test"; done
