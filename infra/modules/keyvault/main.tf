# Key Vault holding service credentials; the App Service reads them via
# Key Vault references instead of raw app settings.

variable "prefix" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "secrets" {
  type      = map(string)
  sensitive = true
}

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                       = replace("${var.prefix}-kv", "_", "-")
  resource_group_name        = var.resource_group_name
  location                   = var.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  tags                       = var.tags
}

resource "azurerm_key_vault_secret" "managed" {
  # Terraform forbids a sensitive for_each, so the marking has to come off
  # somewhere. Un-mark only the NAMES: nonsensitive(var.secrets) would strip
  # the marking from the values too, which is the opposite of what the previous
  # comment here claimed. Values stay marked by indexing back into var.secrets,
  # so Terraform still hard-errors if one is ever used in a non-sensitive
  # position (a tag, a local, an output, a provisioner).
  for_each     = nonsensitive(toset(keys(var.secrets)))
  name         = each.value
  value        = var.secrets[each.value]
  key_vault_id = azurerm_key_vault.main.id
}

output "secret_references" {
  description = "Key Vault references suitable for App Service app settings."
  value = {
    for name, secret in azurerm_key_vault_secret.managed :
    name => "@KeyVault(SecretUri=${secret.id})"
  }
}
