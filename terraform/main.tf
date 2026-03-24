/**
 * # Terraform Module for Secure Token Service Operator
 *
 * This is a Terraform module facilitating the deployment of the secure-token-service charm
 * using the Juju Terraform provider.
 */

resource "juju_application" "application" {
  name        = var.app_name
  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units

  charm {
    name     = "secure-token-service"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
  model_uuid = var.model
}
