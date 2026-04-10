import type { Metadata } from 'next';
import { source } from '@/lib/source';
import { DocPageBody } from '@/components/doc-page';

export default async function HomePage() {
  return <DocPageBody slug={[]} />;
}

export async function generateMetadata(): Promise<Metadata> {
  const page = source.getPage([]);
  if (!page) {
    return { title: 'Humanitec' };
  }
  return {
    title: page.data.title,
    description: page.data.description,
  };
}
