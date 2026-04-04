"use client";

import { Component, ReactNode } from "react";

type Props = { children: ReactNode };
type State = { crashed: boolean; error: string | null };

export default class MessageListErrorBoundary extends Component<Props, State> {
  state: State = { crashed: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { crashed: true, error: error.message };
  }

  render() {
    if (this.state.crashed) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
          <p className="text-sm font-medium text-slate-600">
            Something went wrong displaying the conversation.
          </p>
          <p className="text-xs text-slate-400">{this.state.error}</p>
          <button
            onClick={() => this.setState({ crashed: false, error: null })}
            className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 transition"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
