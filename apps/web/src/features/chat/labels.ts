/**
 * Presentational formatters: raw backend enums never reach the UI untranslated.
 */

export function roleLabel(role: string): string {
  switch (role) {
    case "owner":
      return "Proprietário";
    case "admin":
      return "Administrador";
    case "member":
      return "Membro";
    default:
      return role;
  }
}

export function planLabel(plan: string): string {
  switch (plan) {
    case "free":
      return "Gratuito";
    case "pro":
      return "Pro";
    case "enterprise":
      return "Enterprise";
    default:
      return plan;
  }
}

export function quotaLabel(resource: string): string {
  switch (resource) {
    case "requests":
      return "Solicitações";
    case "input_tokens":
      return "Tokens de entrada";
    case "output_tokens":
      return "Tokens de saída";
    case "total_tokens":
      return "Tokens totais";
    default:
      return resource;
  }
}
