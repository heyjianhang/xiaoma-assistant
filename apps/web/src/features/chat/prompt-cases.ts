import catalog from "@/generated/test-cases.json";

export interface PromptCase {
  id: string;
  category: string;
  group: string;
  label: string;
  question: string;
  required_documents: string[];
  expected_route: string;
  components: string[];
  expected_answer: string;
  checks: string[];
  reference: string[];
}

export const promptCases: PromptCase[] = catalog.cases;
export const promptGroups = catalog.groups;
export const promptSetup = catalog.setup;
export const documentTitles: Record<string, string> = catalog.document_titles;
