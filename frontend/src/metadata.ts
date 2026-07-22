import {useEffect} from "react";

export function usePageMetadata(
  title: string,
  description: string,
  path: string,
  robots?: string,
) {
  useEffect(() => {
    document.title = title;
    const descriptionMeta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    const ogTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    const ogDescription = document.querySelector<HTMLMetaElement>('meta[property="og:description"]');
    const ogUrl = document.querySelector<HTMLMetaElement>('meta[property="og:url"]');
    descriptionMeta?.setAttribute("content", description);
    ogTitle?.setAttribute("content", title);
    ogDescription?.setAttribute("content", description);
    ogUrl?.setAttribute("content", `https://app.mrbarberhub.com.br${path}`);
    let robotsMeta = document.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (robots) {
      if (!robotsMeta) {
        robotsMeta = document.createElement("meta");
        robotsMeta.name = "robots";
        document.head.appendChild(robotsMeta);
      }
      robotsMeta.content = robots;
    }
  }, [description, path, robots, title]);
}
