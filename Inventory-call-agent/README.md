# Inventory-call-agent

ai-calling-agent/
│
├── services/
│   │
│   ├── telephony/
│   │   ├── dialer/
│   │   │   ├── main.py
│   │   │   ├── scheduler.py
│   │   │   ├── call_manager.py
│   │   │   ├── sip_client.py
│   │   │   └── config.py
│   │   │
│   │   ├── livekit_bridge/
│   │   │   ├── room_handler.py
│   │   │   ├── audio_stream.py
│   │   │   ├── call_events.py
│   │   │   └── utils.py
│   │   │
│   │   └── webhooks/
│   │       ├── sip_webhook.py
│   │       └── call_status.py
│   │
│   ├── voice_agent/
│   │   ├── agent_loop.py
│   │   ├── state_machine.py
│   │   ├── memory_manager.py
│   │   ├── prompt_templates/
│   │   ├── intent_parser.py
│   │   ├── action_executor.py
│   │   ├── conversation_controller.py
│   │   │
│   │   ├── stt/
│   │   │   └── sarvam_stt.py
│   │   │
│   │   ├── tts/
│   │   │   └── sarvam_tts.py
│   │   │
│   │   ├── llm/
│   │   │   ├── client.py
│   │   │   └── decision_engine.py
│   │   │
│   │   └── guardrails/
│   │       ├── validation.py
│   │       └── safety_checks.py
│   │
│   ├── business_logic/
│   │   ├── order_service/
│   │   │   ├── api.py
│   │   │   ├── models.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   │
│   │   ├── inventory_service/
│   │   │   ├── api.py
│   │   │   ├── stock_manager.py
│   │   │   └── repository.py
│   │   │
│   │   ├── customer_service/
│   │   │   ├── api.py
│   │   │   └── repository.py
│   │   │
│   │   └── notification_service/
│   │       ├── sms.py
│   │       ├── whatsapp.py
│   │       └── email.py
│   │
│   ├── analytics/
│   │   ├── call_logs.py
│   │   ├── outcome_classifier.py
│   │   └── metrics.py
│   │
│   └── campaign_manager/
│       ├── scheduler.py
│       ├── campaign_api.py
│       └── retry_engine.py
│
├── shared/
│   ├── config/
│   │   ├── settings.py
│   │   └── secrets.py
│   │
│   ├── database/
│   │   ├── mongo_client.py
│   │   └── redis_client.py
│   │
│   ├── schemas/
│   │   ├── call.py
│   │   ├── order.py
│   │   └── customer.py
│   │
│   ├── logging/
│   │   └── logger.py
│   │
│   └── utils/
│       ├── helpers.py
│       └── validators.py
│
├── infrastructure/
│   ├── docker/
│   │   ├── telephony.Dockerfile
│   │   ├── agent.Dockerfile
│   │   └── backend.Dockerfile
│   │
│   ├── docker-compose.yml
│   │
│   ├── terraform/
│   │   ├── aws/
│   │   └── networking/
│   │
│   └── livekit/
│       └── config.yaml
│
├── frontend/
│   ├── dashboard/
│   │   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── api_client/
│   │
│   └── admin_panel/
│
├── monitoring/
│   ├── prometheus.yml
│   ├── grafana_dashboards/
│   └── alerts/
│
├── scripts/
│   ├── seed_database.py
│   ├── start_local.sh
│   └── migrate.py
│
├── tests/
│   ├── telephony/
│   ├── agent/
│   ├── business/
│   └── integration/
│
├── docs/
│   ├── architecture.md
│   ├── api_contracts.md
│   └── onboarding.md
│
├── .env.example
├── requirements.txt
├── Makefile
└── README.md
