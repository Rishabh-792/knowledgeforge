# Linux App Service running the KnowledgeForge API container.

variable "prefix" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "app_settings" { type = map(string) }
variable "log_analytics_workspace_id" { type = string }

resource "azurerm_container_registry" "main" {
  name                = replace("${var.prefix}acr", "-", "")
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false # pulls use the web app's managed identity
  tags                = var.tags
}

resource "azurerm_service_plan" "main" {
  name                = "${var.prefix}-plan"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "P1v3"
  tags                = var.tags
}

resource "azurerm_linux_web_app" "api" {
  name                = "${var.prefix}-api"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true
  tags                = var.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    health_check_path = "/healthz"
    application_stack {
      docker_image_name   = "knowledgeforge:latest"
      docker_registry_url = "https://${azurerm_container_registry.main.login_server}"
    }
  }

  app_settings = merge(var.app_settings, {
    WEBSITES_PORT = "8000"
  })
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_linux_web_app.api.identity[0].principal_id
}

output "default_hostname" {
  value = "https://${azurerm_linux_web_app.api.default_hostname}"
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}
