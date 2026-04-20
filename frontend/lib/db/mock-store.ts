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
  createdAt: Date | null;
  completedAt: Date | null;
  isPanopticon: string;
}

interface MockTodo {
  id: string;
  description: string;
  status: string;
  assignedTo: string | null;
  result: string | null;
  lane: number | null;
}

interface MockAgent {
  id: string;
  name: string;
  sessionId: string;
  status: string;
  currentTaskId: string | null;
  sandboxId: string | null;
  streamUrl: string | null;
  tasksCompleted: number;
  tasksTotal: number;
}

class MockStore {
  sessions = new Map<string, Session>();
  todos = new Map<string, MockTodo[]>();
  agents = new Map<string, MockAgent[]>();

  persistSession(session: Session) {
    this.sessions.set(session.id, session);
  }

  persistTodos(sessionId: string, todoList: Todo[]) {
    const existing = this.todos.get(sessionId) || [];
    const formatted: MockTodo[] = todoList.map(t => ({
      id: t.id,
      description: t.description,
      status: t.status,
      assignedTo: t.assignedTo || null,
      result: t.result || null,
      lane: t.lane ?? null
    }));
    this.todos.set(sessionId, [...existing, ...formatted]);
  }

  replaceTodos(sessionId: string, todoList: Todo[]) {
    const formatted: MockTodo[] = todoList.map(t => ({
      id: t.id,
      description: t.description,
      status: t.status,
      assignedTo: t.assignedTo || null,
      result: t.result || null,
      lane: t.lane ?? null
    }));
    this.todos.set(sessionId, formatted);
  }

  persistAgent(agent: Agent) {
    const sessionAgents = this.agents.get(agent.sessionId) || [];
    const formatted: MockAgent = {
      id: agent.id,
      name: agent.name,
      sessionId: agent.sessionId,
      status: agent.status,
      currentTaskId: agent.currentTaskId || null,
      sandboxId: agent.sandboxId || null,
      streamUrl: agent.streamUrl || null,
      tasksCompleted: agent.tasksCompleted || 0,
      tasksTotal: agent.tasksTotal || 0
    };
    
    // Update if exists, else add
    const index = sessionAgents.findIndex(a => a.id === agent.id);
    if (index >= 0) {
      sessionAgents[index] = formatted;
    } else {
      sessionAgents.push(formatted);
    }
    this.agents.set(agent.sessionId, sessionAgents);
  }

  getAgents(sessionId: string): MockAgent[] {
    return this.agents.get(sessionId) || [];
  }

  getTodos(sessionId: string): MockTodo[] {
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
