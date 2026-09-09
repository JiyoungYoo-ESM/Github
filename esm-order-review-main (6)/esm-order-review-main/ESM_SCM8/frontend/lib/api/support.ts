import { apiFetch, ApiRequestError, FASTAPI_BASE_URL, parseApiError } from "./client";

export type SupportAttachment = {
  id: string;
  original_name: string;
  content_type: string | null;
  size_bytes: number;
};

export type SupportTicket = {
  id: string;
  ticket_number: string;
  requester_name: string;
  requester_team: string | null;
  category: string;
  title: string;
  content: string;
  status: string;
  assignee: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
  attachments: SupportAttachment[];
};

export type SupportTicketSummary = {
  total: number;
  received: number;
  in_progress: number;
  completed: number;
  delayed: number;
};

export type SupportTicketList = {
  items: SupportTicket[];
  summary: SupportTicketSummary;
};

export type CreateSupportTicketInput = {
  requesterName: string;
  requesterTeam?: string;
  category: string;
  title: string;
  content: string;
  attachment?: File | null;
};

export async function getSupportTickets(): Promise<SupportTicketList> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/support/tickets`, {
    method: "GET",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return response.json() as Promise<SupportTicketList>;
}

export async function createSupportTicket(input: CreateSupportTicketInput): Promise<SupportTicket> {
  const form = new FormData();
  form.set("requester_name", input.requesterName);
  if (input.requesterTeam) form.set("requester_team", input.requesterTeam);
  form.set("category", input.category);
  form.set("title", input.title);
  form.set("content", input.content);
  if (input.attachment) form.set("attachment", input.attachment);

  const response = await apiFetch(`${FASTAPI_BASE_URL}/support/tickets`, {
    method: "POST",
    body: form
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return response.json() as Promise<SupportTicket>;
}
