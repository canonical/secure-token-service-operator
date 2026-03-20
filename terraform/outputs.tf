# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.application.name
}

# output "requires" {
#   description = "The Juju integrations that the charm requires"
#   value = {
#     pg-database         = "pg-database"
#     public-route        = "public-route"
#     logging             = "logging"
#     tracing             = "tracing"
#   }
# }
#
# output "provides" {
#   description = "The Juju integrations that the charm provides"
#   value = {
#     metrics-endpoint  = "metrics-endpoint"
#     grafana-dashboard = "grafana-dashboard"
#   }
# }
