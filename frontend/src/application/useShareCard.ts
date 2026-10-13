import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import type { ShareCard } from "@domain/models";
import { buildPostText, parseXPostId } from "@domain/shareCard";
import { renderShareCard } from "@infra/canvas/renderShareCard";

function slugify(text: string): string {
  return (
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "reponse"
  );
}

export function useShareCard(card: Ref<ShareCard | null>) {
  const image = ref<Blob | null>(null);
  const previewUrl = ref<string | null>(null);
  const rendering = ref(false);
  const status = ref<string | null>(null);
  const fallbackLink = ref<string | null>(null);
  const postText = ref("");
  const replyTo = ref("");

  const replyId = computed(() => parseXPostId(replyTo.value));
  const fileName = computed(() => `programme-lisnard-${slugify(card.value?.question ?? "")}.png`);

  function setPreview(blob: Blob | null) {
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = blob ? URL.createObjectURL(blob) : null;
  }

  watch(
    card,
    async (next) => {
      image.value = null;
      setPreview(null);
      status.value = null;
      fallbackLink.value = null;
      if (!next) return;
      postText.value = buildPostText(next);
      rendering.value = true;
      try {
        const blob = await renderShareCard(next, window.location.host);
        if (card.value !== next) return;
        image.value = blob;
        setPreview(blob);
      } catch (e) {
        status.value = e instanceof Error ? e.message : "Impossible de créer l’image.";
      } finally {
        if (card.value === next || !card.value) rendering.value = false;
      }
    },
    { immediate: true },
  );

  onBeforeUnmount(() => setPreview(null));

  function intentUrl(): string {
    const params = new URLSearchParams({ text: postText.value });
    if (replyId.value) params.set("in_reply_to", replyId.value);
    return `https://x.com/intent/tweet?${params}`;
  }

  function download() {
    if (!previewUrl.value) return;
    const a = document.createElement("a");
    a.href = previewUrl.value;
    a.download = fileName.value;
    a.click();
  }

  async function copyImage(blob: Blob): Promise<boolean> {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      return true;
    } catch {
      return false;
    }
  }

  async function shareOnX() {
    const blob = image.value;
    if (!blob) return;
    status.value = null;
    fallbackLink.value = null;

    // Mobile : feuille de partage native, l'image part avec le texte (sauf réponse ciblée)
    const file = new File([blob], fileName.value, { type: "image/png" });
    const touch = window.matchMedia("(pointer: coarse)").matches;
    if (!replyId.value && touch && navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], text: postText.value });
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) {
          status.value = "Le partage a échoué. Copiez l’image puis ajoutez-la à votre post.";
        }
      }
      return;
    }

    // Ordinateur : X ne prend pas d'image par lien → image copiée (ou téléchargée), puis composeur X
    const url = intentUrl();
    const copied = await copyImage(blob);
    if (!copied) download();
    // Pas de "noopener" ici : il ferait renvoyer null même quand l'onglet s'ouvre
    const opened = window.open(url, "_blank");
    if (opened) opened.opener = null;
    const action = replyId.value ? "votre réponse" : "votre post";
    status.value = copied
      ? `Image copiée : collez-la (Ctrl+V / ⌘V) dans ${action} sur X.`
      : `Image téléchargée : ajoutez-la à ${action} sur X.`;
    if (!opened) fallbackLink.value = url;
  }

  async function copyImageToClipboard() {
    const blob = image.value;
    if (!blob) return;
    fallbackLink.value = null;
    if (await copyImage(blob)) {
      status.value = "Image copiée : collez-la (Ctrl+V / ⌘V) où vous voulez.";
    } else {
      download();
      status.value = "Copie d’image impossible sur ce navigateur : image téléchargée.";
    }
  }

  async function copyText() {
    try {
      await navigator.clipboard.writeText(postText.value);
      status.value = "Texte copié.";
    } catch {
      status.value = "Copie impossible : sélectionnez le texte à la main.";
    }
  }

  return {
    previewUrl,
    rendering,
    status,
    fallbackLink,
    replyTo,
    replyId,
    shareOnX,
    copyImageToClipboard,
    copyText,
  };
}
