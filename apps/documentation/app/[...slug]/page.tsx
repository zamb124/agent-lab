import type { Metadata } from 'next';
import { source } from '@/lib/source';
import { DocPageBody } from '@/components/doc-page';
import docPaths from '../../generated/doc-paths.json';

type Params = { slug: string[] };

export function generateStaticParams() {
  return docPaths.slugs.map((slug) => ({ slug }));
}

export default async function Page(props: { params: Promise<Params> }) {
  const { slug } = await props.params;
  return <DocPageBody slug={slug} />;
}

export async function generateMetadata(props: { params: Promise<Params> }): Promise<Metadata> {
  const { slug } = await props.params;
  const page = source.getPage(slug);
  if (!page) {
    return { title: 'Humanitec' };
  }
  return {
    title: page.data.title,
    description: page.data.description,
  };
}
