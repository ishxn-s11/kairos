import WorkDetail from "../../../components/WorkDetail";
import { WORKS } from "../../../lib/data";

export function generateStaticParams() {
  return WORKS.map((w) => ({ stage: `stage-${w.id}` }));
}

export function generateMetadata({ params }) {
  const id = (params.stage || "").replace("stage-", "");
  const wk = WORKS.find((w) => w.id === id) || WORKS[0];
  return { title: `STAGE ${wk.id} ${wk.title} — KAIROS` };
}

export default function StagePage({ params }) {
  const id = (params.stage || "").replace("stage-", "");
  const idx = Math.max(0, WORKS.findIndex((w) => w.id === id));
  return <WorkDetail stage={idx} />;
}
