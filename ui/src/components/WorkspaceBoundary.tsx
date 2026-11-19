import { Component, type ReactNode } from "react";
import { Button } from "../ui";

interface Props { route: string; children: ReactNode }
interface State { route: string; error: string | null }

export class WorkspaceBoundary extends Component<Props, State> {
  state: State = { route: this.props.route, error: null };
  static getDerivedStateFromProps(props: Props, state: State) {
    return props.route !== state.route ? { route: props.route, error: null } : null;
  }
  static getDerivedStateFromError(error: Error) {
    return { error: error.message || "The workspace could not load." };
  }
  render() {
    if (this.state.error) return <section className="tab-empty-state" role="alert">
      <h3>This workspace could not open</h3><p>{this.state.error}</p>
      <Button onClick={() => window.location.reload()}>Reload workspace</Button>
    </section>;
    return this.props.children;
  }
}
