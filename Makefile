docker-build:
	docker image build . -t wallet-runserver:1

docker-up:
	docker compose up $(ARGS)

join-runserver:
	docker exec -it runserver bash

