/**
 * The deterministic decision engine, ported from
 * `backend/app/services/decision_engine.py`.
 *
 * This is a port rather than a mock. The hosted demo has no model behind it,
 * so the agent output is a recording — but the *decision* is still computed by
 * policy code from that output, which is the claim the product actually makes.
 * A canned decision would demo nothing.
 *
 * Kept deliberately faithful to the Python: same rule ids, same stage order,
 * same first-match-wins semantics. If you change one, change both. The Python
 * side is the authority and carries the truth-table tests.
 */

export type AgentStatusValue = "PASS" | "WARNING" | "FAIL" | "BLOCK";
export type DecisionStatusValue = "APPROVED" | "REVISE" | "BLOCKED";
export type SeverityValue = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type DeadlineValue = "FEASIBLE" | "DOUBTFUL" | "INFEASIBLE" | "UNKNOWN" | null;

export interface AgentReviewInput {
  agent: string;
  score: number;
  status: AgentStatusValue;
  confidence: number;
  critical_information_missing: boolean;
  deadline_assessment: DeadlineValue;
  finding_severities: SeverityValue[];
}

export interface DecisionInputs {
  reviews: AgentReviewInput[];
  expectedAgents: string[];
  deadlineIsFixed: boolean;
}

export interface DecisionThresholds {
  confidenceFloor: number;
  warningReviseThreshold: number;
  approveMinAverageScore: number;
  approveMinAgentScore: number;
}

export const DEFAULT_THRESHOLDS: DecisionThresholds = {
  confidenceFloor: 0.6,
  warningReviseThreshold: 3,
  approveMinAverageScore: 75,
  approveMinAgentScore: 60,
};

export interface DecisionResult {
  status: DecisionStatusValue;
  review_complete: boolean;
  deciding_rule_id: string;
  rule_ids: string[];
}

function engineeringAssessment(inputs: DecisionInputs): DeadlineValue {
  // deadline_assessment is meaningful only on ENGINEERING.
  const eng = inputs.reviews.find((r) => r.agent === "ENGINEERING");
  return eng ? eng.deadline_assessment : null;
}

// Stage 1 -- structural completeness only: did every expected reviewer return.
function completenessRules(inputs: DecisionInputs): string[] {
  const returned = new Set(inputs.reviews.map((r) => r.agent));
  const missing = inputs.expectedAgents.some((a) => !returned.has(a));
  return missing ? ["C1_REVIEW_INCOMPLETE"] : [];
}

function blockRules(inputs: DecisionInputs, t: DecisionThresholds): string[] {
  const fired: string[] = [];

  if (inputs.reviews.some((r) => r.status === "BLOCK" && r.confidence >= t.confidenceFloor)) {
    fired.push("B1_AGENT_BLOCK");
  }
  if (
    inputs.reviews.some(
      (r) => r.confidence >= t.confidenceFloor && r.finding_severities.includes("CRITICAL")
    )
  ) {
    fired.push("B2_CRITICAL_FINDING");
  }
  if (inputs.deadlineIsFixed && engineeringAssessment(inputs) === "INFEASIBLE") {
    fired.push("B3_INFEASIBLE_FIXED_DEADLINE");
  }
  return fired;
}

function reviseRules(inputs: DecisionInputs, t: DecisionThresholds): string[] {
  const fired: string[] = [];

  // A BLOCK the agent was not confident about is downgraded, never dropped.
  if (inputs.reviews.some((r) => r.status === "BLOCK" && r.confidence < t.confidenceFloor)) {
    fired.push("R1_LOW_CONFIDENCE_BLOCK");
  }
  if (inputs.reviews.some((r) => r.status === "FAIL")) {
    fired.push("R2_AGENT_FAIL");
  }
  // Moved out of stage 1: an evidence gap must not outrank a confident BLOCK.
  if (inputs.reviews.some((r) => r.critical_information_missing)) {
    fired.push("C2_CRITICAL_INFORMATION_MISSING");
  }
  const warnings = inputs.reviews.filter((r) => r.status === "WARNING").length;
  if (warnings >= t.warningReviseThreshold) {
    fired.push("R3_MULTIPLE_WARNINGS");
  }
  if (inputs.reviews.some((r) => r.finding_severities.includes("HIGH"))) {
    fired.push("R4_HIGH_SEVERITY_FINDING");
  }
  // The counterpart to B2, exactly as R1 is to B1: without it a CRITICAL
  // finding from an unconfident agent matches no rule and can be approved.
  if (
    inputs.reviews.some(
      (r) => r.confidence < t.confidenceFloor && r.finding_severities.includes("CRITICAL")
    )
  ) {
    fired.push("R7_LOW_CONFIDENCE_CRITICAL_FINDING");
  }

  const assessment = engineeringAssessment(inputs);
  if (assessment === "INFEASIBLE" && !inputs.deadlineIsFixed) {
    fired.push("R5_INFEASIBLE_FLEXIBLE_DEADLINE");
  }
  if (assessment === "DOUBTFUL" && inputs.deadlineIsFixed) {
    fired.push("R6_DOUBTFUL_FIXED_DEADLINE");
  }
  return fired;
}

// Score minimums are APPROVE preconditions, deliberately not REVISE triggers --
// that is what leaves the mandatory fallback reachable.
function approvePreconditionsMet(inputs: DecisionInputs, t: DecisionThresholds): boolean {
  if (inputs.reviews.length === 0) return false;
  const scores = inputs.reviews.map((r) => r.score);
  const average = scores.reduce((a, b) => a + b, 0) / scores.length;
  return average >= t.approveMinAverageScore && Math.min(...scores) >= t.approveMinAgentScore;
}

export function evaluate(
  inputs: DecisionInputs,
  thresholds: DecisionThresholds = DEFAULT_THRESHOLDS
): DecisionResult {
  const returned = new Set(inputs.reviews.map((r) => r.agent));
  const reviewComplete = inputs.expectedAgents.every((a) => returned.has(a));

  const completeness = completenessRules(inputs);
  const blocks = blockRules(inputs, thresholds);
  const revises = reviseRules(inputs, thresholds);

  // Every matching rule is recorded in evaluation order regardless of which one
  // decides, so a superseded blocker stays visible rather than being discarded.
  const ruleIds = [...completeness, ...blocks, ...revises];

  if (completeness.length) {
    return {
      status: "REVISE",
      review_complete: reviewComplete,
      deciding_rule_id: completeness[0],
      rule_ids: ruleIds,
    };
  }
  if (blocks.length) {
    return {
      status: "BLOCKED",
      review_complete: reviewComplete,
      deciding_rule_id: blocks[0],
      rule_ids: ruleIds,
    };
  }
  if (revises.length) {
    return {
      status: "REVISE",
      review_complete: reviewComplete,
      deciding_rule_id: revises[0],
      rule_ids: ruleIds,
    };
  }
  if (approvePreconditionsMet(inputs, thresholds)) {
    return {
      status: "APPROVED",
      review_complete: reviewComplete,
      deciding_rule_id: "A1_ALL_CLEAR",
      rule_ids: [...ruleIds, "A1_ALL_CLEAR"],
    };
  }
  // Mandatory. Without it, "no blocker, no fail, two warnings, average 65"
  // matches nothing at all.
  return {
    status: "REVISE",
    review_complete: reviewComplete,
    deciding_rule_id: "F1_FALLBACK_REVISE",
    rule_ids: [...ruleIds, "F1_FALLBACK_REVISE"],
  };
}
