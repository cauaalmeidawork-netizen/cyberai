/**
 * Centralized UI strings for pt-BR locale.
 *
 * All user-facing text lives here so that:
 * 1. Language consistency is enforceable via a single source of truth.
 * 2. Future i18n expansion (en, es, etc.) becomes a matter of adding
 *    a new locale file with the same shape.
 *
 * Usage:
 *   import { t } from "@/lib/i18n/pt-BR";
 *   <span>{t.sidebar.newConversation}</span>
 */

export const t = {
  brand: {
    name: "Nomercy AI",
    tagline: "Como posso ajudar?",
    description:
      "Pesquisa profunda, precisão técnica e respostas com fontes. Especialidade em cybersecurity.",
  },

  sidebar: {
    newConversation: "Nova conversa",
    searchPlaceholder: "Buscar conversas",
    noConversations: "Nenhuma conversa ainda.",
    moreOptions: "Mais opções",
    rename: "Renomear",
    delete: "Excluir",
    close: "Fechar histórico",
  },

  conversationGroups: {
    today: "Hoje",
    yesterday: "Ontem",
    last7Days: "Últimos 7 dias",
    older: "Mais antigos",
  },

  header: {
    newConversation: "Nova conversa",
    openMenu: "Abrir menu",
  },

  composer: {
    placeholder: "Pergunte ao Nomercy",
    send: "Enviar mensagem",
    stop: "Parar geração",
    attachFile: "Anexar arquivo",
    removeAttachment: "Remover anexo",
    model: "Modelo",
  },

  messages: {
    copy: "Copiar",
    regenerate: "Gerar novamente",
    goodResponse: "Boa resposta",
    badResponse: "Resposta ruim",
    generating: "Gerando resposta",
    scrollToBottom: "Rolar para o final",
  },

  sources: {
    label: (count: number) => `Fontes ${count}`,
    sourceLabel: (index: number, title: string) => `Fonte ${index}: ${title}`,
  },

  research: {
    searching: "Pesquisando fontes…",
    querying: (providers: string[]) => {
      const listed = providers.slice(0, 3).join(", ");
      const suffix = providers.length > 3 ? "…" : "";
      return `Consultando ${listed}${suffix}…`;
    },
  },

  settings: {
    title: "Configurações",
    close: "Fechar configurações",
    account: "Conta",
    organization: "Organização",
    role: "Função",
    logout: "Sair",
    usage: "Uso",
    plan: "Plano",
    usageUnavailable: "Informações de uso não disponíveis.",
    about: "Sobre",
    product: "Produto",
    resources: {
      requests: "Requisições",
      input_tokens: "Tokens de entrada",
      output_tokens: "Tokens de saída",
      total_tokens: "Tokens totais",
    },
  },

  auth: {
    loginPrompt:
      "Entre para começar. O navegador recebe apenas um cookie de sessão da aplicação.",
    login: "Entrar",
    sessionExpired: "Sua sessão expirou. Entre novamente.",
  },

  navigation: {
    main: "Navegação principal",
    newConversation: "Nova conversa",
    history: "Histórico",
    openHistory: "Abrir histórico",
    closeHistory: "Fechar histórico",
    settings: "Configurações",
  },

  notices: {
    close: "Fechar aviso",
  },

  suggestions: [
    "Analise este CVE",
    "Explique este log",
    "Compare estas abordagens",
    "Pesquise esta vulnerabilidade",
  ],

  errors: {
    badRequest: "A solicitação não é válida. Revise e tente novamente.",
    unauthorized: "Sua sessão expirou. Entre novamente.",
    forbidden: "Seu acesso atual não permite esta ação.",
    notFound: "O recurso não foi encontrado. Atualize a página.",
    conflict: "Esta ação conflita com o estado atual.",
    tooLarge: "A solicitação é grande demais.",
    tooManyRequests: "Muitas solicitações. Tente novamente em instantes.",
    serviceUnavailable: "O provedor do modelo ou um serviço está indisponível.",
    generic: "Não foi possível concluir. Tente novamente.",
    connectionFailed: "Não foi possível conectar ao serviço.",
    fileReadFailed: "Não foi possível ler o arquivo.",
  },
} as const;
