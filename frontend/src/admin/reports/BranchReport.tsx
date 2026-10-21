import "../../styles/admin.css";

import { ReportView } from "./Reports";

/** Branch head: the same report, limited by the server to their own branch. */
export default function BranchReport() {
  return <ReportView scope="branch" />;
}
