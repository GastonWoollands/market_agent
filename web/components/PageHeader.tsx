type PageHeaderProps = {
  title: string;
  children: string;
};

export function PageHeader({ title, children }: PageHeaderProps) {
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm leading-6 text-mute">{children}</p>
    </div>
  );
}
