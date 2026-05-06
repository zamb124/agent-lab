{{/*
Полное имя образа.
*/}}
{{- define "agentlab.image" -}}
{{- printf "%s:%s" .Values.image.repository (required "agent-lab Helm: задайте image.tag (не используйте подстановку из Chart.AppVersion)" .Values.image.tag) -}}
{{- end -}}

{{/*
Платформенные ENV для всех app/worker подов: URL баз, секреты, OAuth, LLM, S3, push, OnlyOffice, OTLP.
Секреты — из Secret platformSecretName. URL баз — через ClusterIP postgres / redis.
*/}}
{{- define "agentlab.appEnv" -}}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: postgres-password
- name: DATABASE__SHARED_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_shared
- name: DATABASE__FLOWS_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_agents
- name: DATABASE__CRM_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_crm
- name: DATABASE__SYNC_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_sync
- name: DATABASE__RAG_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_rag
- name: DATABASE__OFFICE_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_office
- name: DATABASE__TRACING_URL
  value: postgresql+asyncpg://platform_user:$(POSTGRES_PASSWORD)@{{ .Values.appCommonEnv.postgresService }}:{{ .Values.appCommonEnv.postgresPort }}/platform_tracing
- name: DATABASE__REDIS_URL
  value: redis://{{ .Values.appCommonEnv.redisService }}:{{ .Values.appCommonEnv.redisPort }}/0
- name: DATABASE__AUTO_MIGRATE
  value: "false"
- name: TASKS__BROKER_URL
  value: redis://{{ .Values.appCommonEnv.redisService }}:{{ .Values.appCommonEnv.redisPort }}/1
- name: SERVER__DEBUG
  value: "false"
- name: SERVER__DEPLOYMENT_VERSION
  value: {{ required "agent-lab Helm: задайте image.tag для SERVER__DEPLOYMENT_VERSION" .Values.image.tag | quote }}
- name: SERVER__FLOWS_SERVICE_URL
  value: http://{{ .Values.applications.flows.serviceName }}:{{ .Values.applications.flows.port }}
{{- if .Values.appCommonEnv.flowsWebhookPublicBaseUrl }}
- name: SERVER__FLOWS_WEBHOOK_PUBLIC_BASE_URL
  value: {{ .Values.appCommonEnv.flowsWebhookPublicBaseUrl | quote }}
{{- end }}
- name: SERVER__FRONTEND_SERVICE_URL
  value: http://{{ .Values.applications.frontend.serviceName }}:{{ .Values.applications.frontend.port }}
- name: SERVER__CRM_SERVICE_URL
  value: http://{{ .Values.applications.crm.serviceName }}:{{ .Values.applications.crm.port }}
- name: SERVER__RAG_SERVICE_URL
  value: http://{{ .Values.applications.rag.serviceName }}:{{ .Values.applications.rag.port }}
- name: SERVER__SYNC_SERVICE_URL
  value: http://{{ .Values.applications.sync.serviceName }}:{{ .Values.applications.sync.port }}
- name: SERVER__OFFICE_SERVICE_URL
  value: http://{{ .Values.applications.office.serviceName }}:{{ .Values.applications.office.port }}
- name: SERVER__SCHEDULER_SERVICE_URL
  value: http://{{ index .Values.applications "scheduler-api" "serviceName" }}:{{ index .Values.applications "scheduler-api" "port" }}
{{- $browser := index .Values.applications "browser" }}
{{- if and $browser $browser.enabled }}
- name: SERVER__BROWSER_SERVICE_URL
  value: http://{{ $browser.serviceName }}:{{ $browser.port }}
{{- end }}
{{- $voice := index .Values.applications "voice" }}
{{- if and $voice $voice.enabled }}
- name: SERVER__VOICE_SERVICE_URL
  value: http://{{ $voice.serviceName }}:{{ $voice.port }}
{{- end }}
{{- if .Values.litserve.enabled }}
- name: SERVER__PROVIDER_LITSERVE_SERVICE_URL
  value: http://{{ .Values.litserve.serviceName }}:{{ .Values.litserve.port }}
{{- end }}
- name: SERVER__PLATFORM_PUBLIC_BASE_URL
  value: https://{{ .Values.domain }}
- name: AUTH__JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-jwt-secret
- name: AUTH__PROVIDERS__YANDEX__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-yandex-client-id
      optional: true
- name: AUTH__PROVIDERS__YANDEX__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-yandex-client-secret
      optional: true
- name: AUTH__PROVIDERS__GOOGLE__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-google-client-id
      optional: true
- name: AUTH__PROVIDERS__GOOGLE__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-google-client-secret
      optional: true
- name: AUTH__PROVIDERS__GITHUB__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-github-client-id
      optional: true
- name: AUTH__PROVIDERS__GITHUB__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-github-client-secret
      optional: true
- name: AUTH__PROVIDERS__AMOCRM__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-amocrm-client-id
      optional: true
- name: AUTH__PROVIDERS__AMOCRM__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-amocrm-client-secret
      optional: true
- name: AUTH__PROVIDERS__APPLE__APPLE_PRIVATE_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-apple-private-key
      optional: true
- name: AUTH__DEMO__PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: auth-demo-password
      optional: true
- name: S3__DEFAULT_BUCKET
  value: shvedzilla
- name: S3__BUCKETS__SHVEDZILLA__ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: selectel-access-key
- name: S3__BUCKETS__SHVEDZILLA__SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: selectel-secret-key
- name: PUSH__ENABLED
  value: "true"
- name: PUSH__VAPID_PUBLIC_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: push-vapid-public-key
      optional: true
- name: PUSH__VAPID_PRIVATE_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: push-vapid-private-key
      optional: true
- name: PUSH__VAPID_EMAIL
  value: ops@{{ .Values.domain }}
- name: PUSH__APNS_PRIVATE_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: push-apns-private-key
      optional: true
- name: PUSH__FCM_CREDENTIALS_JSON
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: push-fcm-credentials-json
      optional: true
- name: PUSH__FCM_PROJECT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: push-fcm-project-id
      optional: true
- name: CALLS__LIVEKIT_URL
  value: ws://livekit:7880
- name: CALLS__LIVEKIT_PUBLIC_URL
  value: {{ .Values.livekit.publicUrl | quote }}
- name: CALLS__LIVEKIT_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: livekit-api-key
- name: CALLS__LIVEKIT_API_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: livekit-api-secret
- name: CALLS__TURN_HOST
  value: {{ .Values.domain | quote }}
- name: CALLS__TURN_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: turn-secret
- name: LLM__BOTHUB__API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: llm-bothub-api-key
      optional: true
- name: LLM__OPENROUTER__API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: llm-openrouter-api-key
      optional: true
- name: VOICE__STT__CLOUD_RU__API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: stt-cloud-ru-api-key
      optional: true
- name: VOICE__STT__YANDEX__API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: stt-yandex-api-key
      optional: true
- name: VOICE__STT__YANDEX__FOLDER_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: stt-yandex-folder-id
      optional: true
- name: VOICE__STT__SBER__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: stt-sber-client-id
      optional: true
- name: VOICE__STT__SBER__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: stt-sber-client-secret
      optional: true
- name: VOICE__TTS__CLOUD_RU__API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: tts-cloud-ru-api-key
      optional: true
- name: VOICE__TTS__YANDEX__API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: tts-yandex-api-key
      optional: true
- name: VOICE__TTS__YANDEX__FOLDER_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: tts-yandex-folder-id
      optional: true
- name: VOICE__TTS__SBER__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: tts-sber-client-id
      optional: true
- name: VOICE__TTS__SBER__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: tts-sber-client-secret
      optional: true
- name: RAG__PROVIDERS__PGVECTOR__EMBEDDING_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: rag-embedding-api-key
      optional: true
- name: PROVIDER_LITSERVE__API__BASE_URL
  value: http://{{ .Values.litserve.serviceName }}:{{ .Values.litserve.port }}/v1
- name: OFFICE__DOCUMENT_SERVER_PUBLIC_URL
  value: {{ .Values.onlyoffice.publicUrl | quote }}
- name: OFFICE__JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: onlyoffice-jwt-secret
- name: OFFICE__CALLBACK_PUBLIC_BASE_URL
  value: https://{{ .Values.domain }}
- name: PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCOUNT_NUMBER
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: yoomoney-account-number
      optional: true
- name: PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__NOTIFICATION_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: yoomoney-notification-secret
      optional: true
- name: PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: yoomoney-client-id
      optional: true
- name: PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: yoomoney-client-secret
      optional: true
- name: PAYMENT_PROVIDERS__PROVIDERS__YOOMONEY_MAIN__ACCESS_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.platformSecretName }}
      key: yoomoney-access-token
      optional: true
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: http://alloy:4317
- name: LOGGING__LOKI_QUERY_URL
  value: http://loki:3100
{{- end -}}

{{/*
imagePullSecrets для подов с образом платформы (приватный GHCR и т.п.).
Пустой список — секция не рендерится.
*/}}
{{- define "agentlab.podImagePullSecrets" }}
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Стандартный volumeMount для conf.json (ConfigMap → /app/conf.json).
*/}}
{{- define "agentlab.confVolumeMount" -}}
- name: app-conf
  mountPath: /app/conf.json
  subPath: conf.json
{{- end -}}

{{/*
Стандартный volume для conf.json.
*/}}
{{- define "agentlab.confVolume" -}}
- name: app-conf
  configMap:
    name: {{ .Values.appConfigConfigMap }}
{{- end -}}

{{/*
Универсальный шедулинг пода на конкретную ноду по hostname.
Использование: {{- include "agentlab.nodeSchedule" (list $ "master") | nindent 6 }}
  - nodeName="" или "auto" → nodeSelector не ставится, шедулер выбирает сам (любая нода без taint).
  - nodeName в .Values.gpuNodeNames → добавляется toleration dedicated=gpu:NoSchedule
    и nvidia.com/gpu resource (если .Values.gpuResourceEnabled=true передаётся третьим элементом).
*/}}
{{- define "agentlab.nodeSchedule" -}}
{{- $ctx      := index . 0 -}}
{{- $nodeName := index . 1 -}}
{{- $gpuRes   := false -}}
{{- if gt (len .) 2 -}}{{- $gpuRes = index . 2 -}}{{- end -}}
{{- if and $nodeName (ne $nodeName "auto") -}}
nodeSelector:
  kubernetes.io/hostname: {{ $nodeName | quote }}
{{- $isGpu := false -}}
{{- range $ctx.Values.gpuNodeNames -}}
  {{- if eq . $nodeName -}}{{- $isGpu = true -}}{{- end -}}
{{- end -}}
{{- if $isGpu }}
tolerations:
  - key: dedicated
    operator: Equal
    value: gpu
    effect: NoSchedule
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Init-containers для всех app/worker подов:
  1. wait-postgres — pg_isready на Service postgres:5432 (до 180s).
  2. db-migrate    — `python -m scripts.db_migrate upgrade` для всех сервисных БД.

Alembic держит DDL-блокировку на alembic_version → параллельный старт нескольких pods
не вызывает гонок: один мигрирует, остальные видят head и no-op'ятся.

Использование в Deployment / StatefulSet с доступом к Postgres:
  spec:
    template:
      spec:
        initContainers:
          {{`{{- include "agentlab.dbReadyAndMigrateInitContainers" . | nindent 10 }}`}}
*/}}
{{- define "agentlab.dbReadyAndMigrateInitContainers" -}}
- name: wait-postgres
  image: {{ .Values.postgres.image }}
  imagePullPolicy: IfNotPresent
  env:
    - name: POSTGRES_PASSWORD
      valueFrom:
        secretKeyRef:
          name: {{ .Values.platformSecretName }}
          key: postgres-password
  command:
    - sh
    - -c
    - |
      for i in $(seq 1 90); do
        if PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -h {{ .Values.appCommonEnv.postgresService }} -U platform_user -d postgres -t 2; then
          echo "postgres ready"
          exit 0
        fi
        echo "wait postgres ($i/90)"
        sleep 2
      done
      echo "postgres unavailable after 180s" >&2
      exit 1
- name: db-migrate
  image: {{ include "agentlab.image" . }}
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  command: ["python", "-m", "scripts.db_migrate", "upgrade"]
  env:
    {{- include "agentlab.appEnv" . | nindent 4 }}
  volumeMounts:
    {{- include "agentlab.confVolumeMount" . | nindent 4 }}
{{- end -}}
