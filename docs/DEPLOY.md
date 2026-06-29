# Estratégia de deploy

Use imagens imutáveis para API, worker e beat. Em cloud, prefira PostgreSQL e Redis gerenciados, balanceador com TLS, armazenamento central de logs e autoscaling independente para API e workers. Execute migrations em um job único antes de liberar a nova versão e mantenha rollback da imagem anterior.

Configurações de produção: `core.settings.production`, segredos no secret manager, backups testados, réplicas multi-AZ, health checks, métricas de latência/fila e alertas de disponibilidade. O Celery Beat deve possuir somente uma réplica; os workers podem escalar horizontalmente.
