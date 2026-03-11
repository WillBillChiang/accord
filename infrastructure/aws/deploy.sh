#!/usr/bin/env bash
# =============================================================================
# Accord TEE Negotiation Engine - Infrastructure Deployment Script
#
# Deploys all CloudFormation stacks in dependency order with validation,
# error handling, and proper wait behavior.
#
# Usage:
#   ./deploy.sh                          # Deploy with defaults (prod)
#   ./deploy.sh --env dev                # Deploy to dev environment
#   ./deploy.sh --env staging --region us-west-2
#   ./deploy.sh --env prod --acm-cert arn:aws:acm:...
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#   - Sufficient IAM permissions to create all resources
#   - ACM certificate ARN for the ALB HTTPS listener
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration & Defaults
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="prod"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACM_CERT_ARN=""
GITHUB_REPO=""
GITHUB_BRANCH="main"
GITHUB_TOKEN=""
ALERT_EMAIL=""
PCR0=""
PCR1=""
PCR2=""
SKIP_VALIDATION=false
DRY_RUN=false

# Stack naming convention
stack_name() {
    echo "accord-${ENV}-${1}"
}

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}[INFO]${NC}  $(date '+%H:%M:%S') $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $(date '+%H:%M:%S') $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $(date '+%H:%M:%S') $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S') $*"; }

# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------
usage() {
    cat <<USAGE
Usage: $(basename "$0") [OPTIONS]

Options:
  --env ENV              Environment name: dev, staging, prod (default: prod)
  --region REGION        AWS region (default: us-east-1 or AWS_DEFAULT_REGION)
  --acm-cert ARN        ACM certificate ARN for ALB HTTPS listener (required for compute)
  --github-repo URL     GitHub repository URL (required for amplify)
  --github-branch NAME  GitHub branch (default: main)
  --github-token TOKEN  GitHub personal access token (required for amplify)
  --alert-email EMAIL   Email for CloudWatch alarm notifications
  --pcr0 VALUE          PCR0 attestation value for KMS key policy
  --pcr1 VALUE          PCR1 attestation value for KMS key policy
  --pcr2 VALUE          PCR2 attestation value for KMS key policy
  --skip-validation     Skip CloudFormation template validation
  --dry-run             Validate templates only, do not deploy
  -h, --help            Show this help message

Examples:
  $(basename "$0") --env dev --acm-cert arn:aws:acm:us-east-1:123456789012:certificate/abc-123
  $(basename "$0") --env prod --acm-cert arn:aws:acm:... --github-repo https://github.com/org/accord --github-token ghp_xxx
USAGE
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)          ENV="$2"; shift 2 ;;
        --region)       REGION="$2"; shift 2 ;;
        --acm-cert)     ACM_CERT_ARN="$2"; shift 2 ;;
        --github-repo)  GITHUB_REPO="$2"; shift 2 ;;
        --github-branch) GITHUB_BRANCH="$2"; shift 2 ;;
        --github-token) GITHUB_TOKEN="$2"; shift 2 ;;
        --alert-email)  ALERT_EMAIL="$2"; shift 2 ;;
        --pcr0)         PCR0="$2"; shift 2 ;;
        --pcr1)         PCR1="$2"; shift 2 ;;
        --pcr2)         PCR2="$2"; shift 2 ;;
        --skip-validation) SKIP_VALIDATION=true; shift ;;
        --dry-run)      DRY_RUN=true; shift ;;
        -h|--help)      usage ;;
        *)              log_error "Unknown option: $1"; usage ;;
    esac
done

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
validate_prerequisites() {
    log_info "Validating prerequisites..."

    # Check AWS CLI
    if ! command -v aws &>/dev/null; then
        log_error "AWS CLI is not installed. Install it from https://aws.amazon.com/cli/"
        exit 1
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity --region "$REGION" &>/dev/null; then
        log_error "AWS credentials are not configured or are invalid."
        exit 1
    fi

    local account_id
    account_id=$(aws sts get-caller-identity --query "Account" --output text --region "$REGION")
    log_info "AWS Account: ${account_id}"
    log_info "Region:      ${REGION}"
    log_info "Environment: ${ENV}"

    # Validate environment
    if [[ "$ENV" != "dev" && "$ENV" != "staging" && "$ENV" != "prod" ]]; then
        log_error "Invalid environment: ${ENV}. Must be dev, staging, or prod."
        exit 1
    fi

    # Check template files exist
    local templates=("network.yaml" "security.yaml" "auth.yaml" "data.yaml" "compute.yaml" "monitoring.yaml" "amplify.yaml")
    for tmpl in "${templates[@]}"; do
        if [[ ! -f "${SCRIPT_DIR}/${tmpl}" ]]; then
            log_error "Template file not found: ${SCRIPT_DIR}/${tmpl}"
            exit 1
        fi
    done

    log_success "Prerequisites validated."
}

# -----------------------------------------------------------------------------
# Template Validation
# -----------------------------------------------------------------------------
validate_templates() {
    if [[ "$SKIP_VALIDATION" == true ]]; then
        log_warn "Skipping template validation (--skip-validation)"
        return 0
    fi

    log_info "Validating CloudFormation templates..."

    local templates=("network.yaml" "security.yaml" "auth.yaml" "data.yaml" "compute.yaml" "monitoring.yaml" "amplify.yaml")
    local failed=false

    for tmpl in "${templates[@]}"; do
        if aws cloudformation validate-template \
            --template-body "file://${SCRIPT_DIR}/${tmpl}" \
            --region "$REGION" &>/dev/null; then
            log_success "  ${tmpl} - valid"
        else
            log_error "  ${tmpl} - INVALID"
            aws cloudformation validate-template \
                --template-body "file://${SCRIPT_DIR}/${tmpl}" \
                --region "$REGION" 2>&1 || true
            failed=true
        fi
    done

    if [[ "$failed" == true ]]; then
        log_error "Template validation failed. Fix errors before deploying."
        exit 1
    fi

    log_success "All templates validated successfully."
}

# -----------------------------------------------------------------------------
# Stack Deployment
# -----------------------------------------------------------------------------
deploy_stack() {
    local stack_logical_name="$1"
    local template_file="$2"
    shift 2
    local params=("$@")

    local full_stack_name
    full_stack_name=$(stack_name "$stack_logical_name")

    log_info "Deploying stack: ${full_stack_name}"

    # Check if stack already exists
    local stack_status=""
    stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$full_stack_name" \
        --region "$REGION" \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null || echo "DOES_NOT_EXIST")

    local action="create"
    if [[ "$stack_status" != "DOES_NOT_EXIST" ]]; then
        case "$stack_status" in
            CREATE_COMPLETE|UPDATE_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
                action="update"
                log_info "  Stack exists (${stack_status}), updating..."
                ;;
            ROLLBACK_COMPLETE|CREATE_FAILED)
                log_warn "  Stack is in ${stack_status} state. Deleting and recreating..."
                aws cloudformation delete-stack \
                    --stack-name "$full_stack_name" \
                    --region "$REGION"
                aws cloudformation wait stack-delete-complete \
                    --stack-name "$full_stack_name" \
                    --region "$REGION"
                action="create"
                ;;
            *_IN_PROGRESS)
                log_error "  Stack is in ${stack_status} state. Wait for it to complete."
                exit 1
                ;;
            *)
                log_warn "  Stack is in ${stack_status} state. Attempting update..."
                action="update"
                ;;
        esac
    fi

    # Build the deploy command
    local cmd=(
        aws cloudformation deploy
        --stack-name "$full_stack_name"
        --template-file "${SCRIPT_DIR}/${template_file}"
        --region "$REGION"
        --capabilities CAPABILITY_NAMED_IAM
        --no-fail-on-empty-changeset
        --tags
            "Environment=${ENV}"
            "Project=accord"
            "ManagedBy=cloudformation"
    )

    # Add parameter overrides if provided
    if [[ ${#params[@]} -gt 0 ]]; then
        cmd+=(--parameter-overrides "${params[@]}")
    fi

    # Execute deployment
    if "${cmd[@]}"; then
        log_success "Stack ${full_stack_name} deployed successfully."
    else
        local final_status
        final_status=$(aws cloudformation describe-stacks \
            --stack-name "$full_stack_name" \
            --region "$REGION" \
            --query "Stacks[0].StackStatus" \
            --output text 2>/dev/null || echo "UNKNOWN")

        log_error "Stack ${full_stack_name} deployment failed (status: ${final_status})."

        # Show failure events
        log_error "Recent failure events:"
        aws cloudformation describe-stack-events \
            --stack-name "$full_stack_name" \
            --region "$REGION" \
            --query "StackEvents[?ResourceStatus=='CREATE_FAILED' || ResourceStatus=='UPDATE_FAILED'].[LogicalResourceId,ResourceStatusReason]" \
            --output table 2>/dev/null || true

        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Main Deployment Orchestration
# -----------------------------------------------------------------------------
main() {
    echo ""
    echo "============================================================"
    echo "  Accord TEE Negotiation Engine - Infrastructure Deployment"
    echo "  Environment: ${ENV} | Region: ${REGION}"
    echo "============================================================"
    echo ""

    validate_prerequisites
    validate_templates

    if [[ "$DRY_RUN" == true ]]; then
        log_info "Dry run mode - templates validated, skipping deployment."
        exit 0
    fi

    local start_time
    start_time=$(date +%s)

    # ---- 1. Network Stack ----
    log_info "========== [1/7] Network =========="
    deploy_stack "network" "network.yaml" \
        "EnvironmentName=${ENV}"

    # ---- 2. Security Stack ----
    log_info "========== [2/7] Security =========="
    local security_params=("EnvironmentName=${ENV}")
    if [[ -n "$PCR0" ]]; then security_params+=("ExpectedPCR0=${PCR0}"); fi
    if [[ -n "$PCR1" ]]; then security_params+=("ExpectedPCR1=${PCR1}"); fi
    if [[ -n "$PCR2" ]]; then security_params+=("ExpectedPCR2=${PCR2}"); fi
    deploy_stack "security" "security.yaml" "${security_params[@]}"

    # ---- 3. Auth Stack ----
    log_info "========== [3/7] Auth =========="
    deploy_stack "auth" "auth.yaml" \
        "EnvironmentName=${ENV}"

    # ---- 4. Data Stack ----
    log_info "========== [4/7] Data =========="
    deploy_stack "data" "data.yaml" \
        "EnvironmentName=${ENV}"

    # ---- 5. Compute Stack ----
    log_info "========== [5/7] Compute =========="
    if [[ -z "$ACM_CERT_ARN" ]]; then
        log_warn "No ACM certificate ARN provided (--acm-cert). Skipping compute stack."
        log_warn "Re-run with --acm-cert to deploy the compute layer."
    else
        deploy_stack "compute" "compute.yaml" \
            "EnvironmentName=${ENV}" \
            "ACMCertificateArn=${ACM_CERT_ARN}"
    fi

    # ---- 6. Monitoring Stack ----
    log_info "========== [6/7] Monitoring =========="
    if [[ -z "$ACM_CERT_ARN" ]]; then
        log_warn "Skipping monitoring stack (depends on compute stack)."
    else
        local monitoring_params=("EnvironmentName=${ENV}")
        if [[ -n "$ALERT_EMAIL" ]]; then
            monitoring_params+=("AlertEmail=${ALERT_EMAIL}")
        fi
        deploy_stack "monitoring" "monitoring.yaml" "${monitoring_params[@]}"
    fi

    # ---- 7. Amplify Stack ----
    log_info "========== [7/7] Amplify =========="
    if [[ -z "$GITHUB_REPO" || -z "$GITHUB_TOKEN" ]]; then
        log_warn "GitHub repo and/or token not provided. Skipping Amplify stack."
        log_warn "Re-run with --github-repo and --github-token to deploy the frontend."
    else
        if [[ -z "$ACM_CERT_ARN" ]]; then
            log_warn "Skipping Amplify stack (depends on compute stack for ALB DNS)."
        else
            deploy_stack "amplify" "amplify.yaml" \
                "EnvironmentName=${ENV}" \
                "GitHubRepo=${GITHUB_REPO}" \
                "GitHubBranch=${GITHUB_BRANCH}" \
                "GitHubToken=${GITHUB_TOKEN}"
        fi
    fi

    # ---- Summary ----
    local end_time
    end_time=$(date +%s)
    local duration=$(( end_time - start_time ))
    local minutes=$(( duration / 60 ))
    local seconds=$(( duration % 60 ))

    echo ""
    echo "============================================================"
    echo "  Deployment Complete"
    echo "============================================================"
    log_success "Environment: ${ENV}"
    log_success "Region:      ${REGION}"
    log_success "Duration:    ${minutes}m ${seconds}s"
    echo ""

    # Print stack outputs
    log_info "Stack Outputs:"
    echo ""

    local stacks=("network" "security" "auth" "data")
    if [[ -n "$ACM_CERT_ARN" ]]; then
        stacks+=("compute" "monitoring")
    fi
    if [[ -n "$GITHUB_REPO" && -n "$GITHUB_TOKEN" && -n "$ACM_CERT_ARN" ]]; then
        stacks+=("amplify")
    fi

    for s in "${stacks[@]}"; do
        local sn
        sn=$(stack_name "$s")
        log_info "  --- ${sn} ---"
        aws cloudformation describe-stacks \
            --stack-name "$sn" \
            --region "$REGION" \
            --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
            --output table 2>/dev/null || log_warn "  Could not retrieve outputs for ${sn}"
        echo ""
    done

    log_success "Accord infrastructure deployment finished."
}

main "$@"
