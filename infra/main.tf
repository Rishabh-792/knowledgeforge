# KnowledgeForge infrastructure — Terraform (azurerm).
#
# One resource group containing: AI Search, an OpenAI cognitive account with
# chat + embedding deployments, blob storage for batch ingestion, Key Vault
# for secrets, Log Analytics + Application Insights, and a Linux App Service
# running the API container.
#
# Usage:
#   terraform init && terraform apply -var env=dev

terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.1"
    }
  }
}

provider "azurerm" {
  features {}
  # Required from azurerm 4.0 onward. `terraform validate` does not configure
  # the provider, so a missing value passes CI and then fails on the first real
  # plan — set it here or via ARM_SUBSCRIPTION_ID.
  subscription_id = var.subscription_id
}

variable "subscription_id" {
  type        = string
  default     = null
  description = "Azure subscription ID. Falls back to ARM_SUBSCRIPTION_ID when null."
}

variable "env" {
  type        = string
  default     = "dev"
  description = "Environment name used in resource naming."
}

variable "location" {
  type    = string
  default = "westeurope"
}

locals {
  prefix = "kforge-${var.env}"
  tags = {
    project = "knowledgeforge"
    env     = var.env
  }
}

resource "azurerm_resource_group" "main" {
  name     = "${local.prefix}-rg"
  location = var.location
  tags     = local.tags
}

module "loganalytics" {
  source              = "./modules/loganalytics"
  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
}

module "storage" {
  source              = "./modules/storage"
  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
}

module "search" {
  source              = "./modules/search"
  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
}

module "openai" {
  source              = "./modules/openai"
  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
}

module "keyvault" {
  source              = "./modules/keyvault"
  prefix              = local.prefix
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  secrets = {
    azure-search-api-key = module.search.admin_key
    azure-openai-api-key = module.openai.api_key
  }
}

module "appservice" {
  source                     = "./modules/appservice"
  prefix                     = local.prefix
  resource_group_name        = azurerm_resource_group.main.name
  location                   = var.location
  tags                       = local.tags
  log_analytics_workspace_id = module.loganalytics.workspace_id
  app_settings = {
    AZURE_SEARCH_ENDPOINT                 = module.search.endpoint
    AZURE_SEARCH_API_KEY                  = module.keyvault.secret_references["azure-search-api-key"]
    AZURE_OPENAI_ENDPOINT                 = module.openai.endpoint
    AZURE_OPENAI_API_KEY                  = module.keyvault.secret_references["azure-openai-api-key"]
    APPLICATIONINSIGHTS_CONNECTION_STRING = module.loganalytics.app_insights_connection_string
  }
}

output "api_url" {
  value = module.appservice.default_hostname
}

output "search_endpoint" {
  value = module.search.endpoint
}
