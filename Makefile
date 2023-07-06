.PHONY: build

Q 	= @

BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_VERSION := $(shell grep "^## " CHANGELOG.md | cut -d "[" -f2 | cut -d "]" -f1)
BUILD_GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
BUILD_GIT_COMMIT := $(shell git rev-parse --short HEAD)
BUILD_GIT_STATUS := $(shell ./.git-status.sh)

all:
	${Q} echo "no default target!"

build:
	${Q} docker compose build \
		--build-arg BUILD_TIME=${BUILD_TIME} \
		--build-arg BUILD_VERSION=${BUILD_VERSION} \
		--build-arg BUILD_GIT_BRANCH=${BUILD_GIT_BRANCH} \
		--build-arg BUILD_GIT_COMMIT=${BUILD_GIT_COMMIT} \
		--build-arg BUILD_GIT_STATUS=${BUILD_GIT_STATUS}

run-dev:
	${Q} docker compose --env-file config/env-dev up --abort-on-container-exit --exit-code-from crawler

run:
	${Q} docker compose up --abort-on-container-exit --exit-code-from crawler
