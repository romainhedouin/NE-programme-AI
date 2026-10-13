import { ref } from "vue";
import type { ChatResult, ProgrammeSource, QueryMode, RetrievalMode } from "@domain/models";
import { programmeRepository } from "@infra/container";
import { ApiError } from "@infra/http/apiClient";

export function useProgrammeQuery() {
  const mode = ref<QueryMode>("ask");
  const query = ref("");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const answer = ref<string | null>(null);
  const sources = ref<ProgrammeSource[]>([]);
  const retrieval = ref<RetrievalMode | null>(null);
  const hasResult = ref(false);
  const found = ref(false);
  const askedQuestion = ref("");
  let seq = 0;

  function setMode(next: QueryMode) {
    seq++;
    loading.value = false;
    mode.value = next;
    error.value = null;
    answer.value = null;
    sources.value = [];
    retrieval.value = null;
    hasResult.value = false;
    found.value = false;
  }

  async function submit() {
    const q = query.value.trim();
    if (q.length < 3 || loading.value) return;

    const id = ++seq;
    loading.value = true;
    error.value = null;
    hasResult.value = false;
    answer.value = null;
    sources.value = [];
    retrieval.value = null;
    found.value = false;
    askedQuestion.value = q;

    try {
      if (mode.value === "ask") {
        const result: ChatResult = await programmeRepository.ask(q);
        if (id !== seq) return;
        answer.value = result.answer;
        sources.value = result.sources;
        retrieval.value = result.retrieval;
        found.value = result.found;
      } else {
        const result = await programmeRepository.search(q);
        if (id !== seq) return;
        sources.value = result.results;
        retrieval.value = result.retrieval;
        if (!result.results.length) {
          answer.value = "Aucun passage trouvé dans le programme officiel.";
        }
      }
      hasResult.value = true;
    } catch (e) {
      if (id !== seq) return;
      error.value =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Impossible de joindre l’API.";
      hasResult.value = true;
    } finally {
      if (id === seq) loading.value = false;
    }
  }

  return {
    mode,
    query,
    loading,
    error,
    answer,
    sources,
    retrieval,
    hasResult,
    found,
    askedQuestion,
    setMode,
    submit,
  };
}
