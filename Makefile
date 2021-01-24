
.PHONY: deploy

all: update deploy

deploy:
	find app/ -type f -name 'requirements.txt' -exec cat '{}' '+' > requirements.txt
	docker-compose up --build -d

update:
	git pull
	git submodule update
