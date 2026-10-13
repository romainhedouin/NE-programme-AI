import { ref, onMounted } from "vue";
import type { CorpusHealth } from "@domain/models";
import { programmeRepository } from "@infra/container";

export function useHealth() {
  const health = ref<CorpusHealth | null>(null);
  const loading = ref(true);
  const error = ref<string | null>(null);

  async function refresh() {
    loading.value = true;
    error.value = null;
    try {
      health.value = await programmeRepository.getHealth();
      if (!health.value.ok) {
        error.value = health.value.error ?? "Le programme est momentanément indisponible.";
      }
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : "Serveur injoignable. Réessayez dans un instant.";
      health.value = null;
    } finally {
      loading.value = false;
    }
  }

  onMounted(refresh);

  return { health, loading, error, refresh };
}
