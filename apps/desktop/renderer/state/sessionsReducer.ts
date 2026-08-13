import type { SessionRow } from "../lib/types";

export type SessionsState = {
  sessions: SessionRow[];
  sessionId: string | null;
};

export const initialSessionsState: SessionsState = {
  sessions: [],
  sessionId: null,
};

export type SessionsAction =
  | { type: "setList"; sessions: SessionRow[] }
  | { type: "select"; sessionId: string | null }
  | { type: "removed"; sessionId: string }
  | { type: "clearAll" };

export function sessionsReducer(
  state: SessionsState,
  action: SessionsAction
): SessionsState {
  switch (action.type) {
    case "setList":
      return { ...state, sessions: action.sessions };

    case "select":
      return { ...state, sessionId: action.sessionId };

    case "removed":
      return {
        sessions: state.sessions.filter(
          (s) => s.session_id !== action.sessionId
        ),
        sessionId:
          state.sessionId === action.sessionId ? null : state.sessionId,
      };

    case "clearAll":
      return initialSessionsState;

    default:
      return state;
  }
}
