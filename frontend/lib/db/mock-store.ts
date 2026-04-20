/**
 * In-memory fallback store for sessions, todos, and agents.
 * Used when DATABASE_URL is not configured.
 */
import type { Todo, Agent } from "../types";

interface Session {
  id: string;
  userId: string | null;
  prompt: string;
  agentCount: number;
  status: string;
  createdAt: Date;
  completedAt?: Date;
  isPanopticon: string;
}

class MockStore {
  sessions = new Map<string, Session>();
  todos = new Map<string, Todo[]>();
  agents = new Map<string, Agent[]>();

  persistSession(session: Session) {
    this.sessions.set(session.id, session);
  }

  persistTodos(sessionId: string, todoList: Todo[]) {
    const existing = this.todos.get(sessionId) || [];
    this.todos.set(sessionId, [...existing, ...todoList]);
  }

  replaceTodos(sessionId: string, todoList: Todo[]) {
    this.todos.set(sessionId, todoList);
  }

  persistAgent(agent: Agent) {
    const sessionAgents = this.agents.get(agent.sessionId) || [];
    // Update if exists, else add
    const index = sessionAgents.findIndex(a => a.id === agent.id);
    if (index >= 0) {
      sessionAgents[index] = agent;
    } else {
      sessionAgents.push(agent);
    }
    this.agents.set(agent.sessionId, sessionAgents);
  }

  getAgents(sessionId: string): Agent[] {
    return this.agents.get(sessionId) || [];
  }

  getTodos(sessionId: string): Todo[] {
    return this.todos.get(sessionId) || [];
  }

  getSession(sessionId: string) {
    return this.sessions.get(sessionId);
  }

  updateSession(sessionId: string, updates: Partial<Session>) {
    const session = this.sessions.get(sessionId);
    if (session) {
      this.sessions.set(sessionId, { ...session, ...updates });
    }
  }

  updateTodoStatus(todoId: string, status: string, result?: string) {
    // Search through all session todo lists
    for (const [sessionId, todoList] of this.todos.entries()) {
      const todo = todoList.find(t => t.id === todoId);
      if (todo) {
        todo.status = status as any;
        if (result) todo.result = result;
        return;
      }
    }
  }
}

// Global singleton
export const mockStore = new MockStore();
