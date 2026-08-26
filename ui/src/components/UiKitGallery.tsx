import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Dialog,
  Kpi,
  Tabs,
  Tooltip,
} from "../ui";
import type { BadgeTone } from "../ui";
import styles from "./UiKitGallery.module.css";

const BADGE_TONES: BadgeTone[] = [
  "neutral",
  "accent",
  "ready",
  "review",
  "high",
  "medium",
  "success",
];

/**
 * Living gallery of the shared UI-kit primitives (reachable at #/ui-kit).
 *
 * Renders every primitive and variant so they can be visually verified against
 * any active theme. This is the in-app, air-gap-friendly analogue of a
 * Storybook canvas and doubles as documentation for the design system.
 */
export function UiKitGallery() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className={styles.page}>
      <div className={styles.intro}>
        <h2>Audiotheca UI kit</h2>
        <p>
          Radix-backed, token-driven primitives that re-theme with every built-in and custom
          theme. This gallery is the adoption target for migrating existing screens without
          changing any Audiotheca functionality.
        </p>
      </div>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Buttons</h3>
        <div className={styles.row}>
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="secondary" active>
            Active
          </Button>
          <Button variant="icon" aria-label="Icon button">
            ◐
          </Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
        <div className={styles.row}>
          <Button size="sm" variant="primary">
            Small primary
          </Button>
          <Button size="sm" variant="secondary">
            Small secondary
          </Button>
          <Button size="sm" variant="danger">
            Small danger
          </Button>
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Badges</h3>
        <div className={styles.row}>
          {BADGE_TONES.map((tone) => (
            <Badge key={tone} tone={tone}>
              {tone}
            </Badge>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>KPIs</h3>
        <div className={styles.grid}>
          <Kpi label="Scanned" value={(1284).toLocaleString()} hint="items this run" />
          <Kpi label="Route ready" value="58%" tone="ready" />
          <Kpi label="Needs review" value="12" tone="review" />
          <Kpi label="Scan failures" value="1" tone="danger" />
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Cards</h3>
        <div className={styles.grid}>
          <Card>
            <CardHeader title="Duplicates & archives" subtitle="dedupe + coexistence" />
            <CardBody>
              <div className={styles.row}>
                <Badge tone="high">3 groups</Badge>
                <Badge tone="ready">keeper set</Badge>
              </div>
            </CardBody>
          </Card>
          <Card elevated>
            <CardHeader
              title="Elevated card"
              subtitle="with actions"
              actions={
                <Button size="sm" variant="secondary">
                  Action
                </Button>
              }
            />
            <CardBody>Panels, KPIs and review rows can be composed from these.</CardBody>
          </Card>
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Tabs</h3>
        <Tabs
          aria-label="Sample tabs"
          items={[
            { value: "overview", label: "Overview", content: <p>Overview content.</p> },
            { value: "details", label: "Details", content: <p>Details content.</p> },
            { value: "audit", label: "Audit", content: <p>Audit content.</p> },
          ]}
        />
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Overlays</h3>
        <div className={styles.row}>
          <Tooltip content="Radix-powered tooltip, themed via tokens.">
            <Button variant="secondary">Hover for tooltip</Button>
          </Tooltip>
          <Button variant="primary" onClick={() => setDialogOpen(true)}>
            Open dialog
          </Button>
          <Dialog
            open={dialogOpen}
            onOpenChange={setDialogOpen}
            title="Confirm live action"
            description="Radix Dialog with focus trap, escape-to-close and overlay."
            footer={
              <div className={styles.row}>
                <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button variant="danger" onClick={() => setDialogOpen(false)}>
                  Proceed
                </Button>
              </div>
            }
          >
            <p style={{ color: "var(--ui-fg-muted)", fontSize: "var(--ui-fs-sm)" }}>
              Dialogs replace the ad-hoc modal markup with an accessible primitive.
            </p>
          </Dialog>
        </div>
      </section>
    </div>
  );
}
