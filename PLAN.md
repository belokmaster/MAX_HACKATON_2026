Архитектура beta version:

├── .dockerignore
├── .gitignore
├── .env.example # без реальных токенов/ключей!!!!! СТРОГО
├── docker-compose.yml
├── README.md
│
├── bot/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│
├── webapp/Bridge)
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│
├── api/
│   ├── Dockerfile
│   ├── openapi.yaml
│   ├── DATA-API.yaml
│   ├── requirements.txt
│   └── src/
│
└── test_data/

Еще важно учесть, что сборка через Docker должна занимать не более 5 минут. НА БУДУЩЕЕ

остальное на диме
