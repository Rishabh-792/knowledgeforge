# Azure AI Search — hosts the hybrid (vector + BM25) chunk index.

variable "prefix" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }

resource "azurerm_search_service" "main" {
  name                = "${var.prefix}-search"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "basic" # standard+ for production replica/partition scaling
  partition_count     = 1
  replica_count       = 1
  tags                = var.tags
}

output "endpoint" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "admin_key" {
  value     = azurerm_search_service.main.primary_key
  sensitive = true
}
