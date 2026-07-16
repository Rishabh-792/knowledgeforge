# Blob storage for the batch ingestion pipeline (incoming-docs container).

variable "prefix" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_storage_account" "main" {
  # Storage names: lowercase alphanumeric only, max 24 chars.
  name                     = replace("${var.prefix}sa", "-", "")
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS" # ZRS/GRS for production durability targets
  min_tls_version          = "TLS1_2"
  tags                     = var.tags
}

resource "azurerm_storage_container" "incoming" {
  name                  = "incoming-docs"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

output "connection_string" {
  value     = azurerm_storage_account.main.primary_connection_string
  sensitive = true
}
