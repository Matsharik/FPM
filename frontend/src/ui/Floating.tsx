// Поповер, меню и тултип на @floating-ui/react (клавиатура, Esc, клик снаружи).
import {
  FloatingFocusManager,
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useClick,
  useDismiss,
  useFloating,
  useFocus,
  useHover,
  useInteractions,
  useRole,
  type Placement,
} from '@floating-ui/react';
import { cloneElement, isValidElement, useState, type ReactElement, type ReactNode } from 'react';
import s from './ui.module.css';

type TriggerProps = Record<string, unknown>;

export function Popover({
  trigger,
  children,
  placement = 'bottom-start',
  role = 'dialog',
  className,
}: {
  trigger: ReactElement<TriggerProps>;
  children: ReactNode | ((close: () => void) => ReactNode);
  placement?: Placement;
  role?: 'dialog' | 'menu';
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement,
    middleware: [offset(8), flip(), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate,
  });
  const { getReferenceProps, getFloatingProps } = useInteractions([useClick(context), useDismiss(context), useRole(context, { role })]);
  const close = () => setOpen(false);
  if (!isValidElement(trigger)) return null;
  return (
    <>
      {cloneElement(trigger, {
        ref: refs.setReference,
        ...getReferenceProps({
          ...(trigger.props as React.HTMLProps<Element>),
          onClick: (e: React.MouseEvent<Element>) => {
            e.stopPropagation();
            (trigger.props as React.HTMLProps<Element>).onClick?.(e as React.MouseEvent<HTMLElement>);
          },
        }),
      } as TriggerProps)}
      {open ? (
        <FloatingPortal>
          <FloatingFocusManager context={context} modal={false} initialFocus={-1}>
            <div
              ref={refs.setFloating}
              style={floatingStyles}
              className={className ?? (role === 'menu' ? s.menu : s.popover)}
              {...getFloatingProps({ onClick: (e: React.MouseEvent) => e.stopPropagation() })}
            >
              {typeof children === 'function' ? children(close) : children}
            </div>
          </FloatingFocusManager>
        </FloatingPortal>
      ) : null}
    </>
  );
}

export function Tooltip({ content, children, placement = 'top' }: { content: ReactNode; children: ReactElement<TriggerProps>; placement?: Placement }) {
  const [open, setOpen] = useState(false);
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement,
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });
  const { getReferenceProps, getFloatingProps } = useInteractions([
    useHover(context, { delay: { open: 250, close: 0 } }),
    useFocus(context),
    useDismiss(context),
    useRole(context, { role: 'tooltip' }),
  ]);
  if (!isValidElement(children)) return null;
  return (
    <>
      {/* Свои обработчики дочернего элемента (onClick, onKeyDown) передаём внутрь, чтобы floating-ui их слил, а не затёр. */}
      {cloneElement(children, { ref: refs.setReference, ...getReferenceProps(children.props as React.HTMLProps<Element>) } as TriggerProps)}
      {open && content ? (
        <FloatingPortal>
          <div ref={refs.setFloating} style={floatingStyles} className={s.tooltip} {...getFloatingProps()}>
            {content}
          </div>
        </FloatingPortal>
      ) : null}
    </>
  );
}

export function MenuItem({ children, onClick, active, icon }: { children: ReactNode; onClick: () => void; active?: boolean; icon?: ReactNode }) {
  return (
    <button type="button" role="menuitem" className={`${s.menuItem} ${active ? s.menuItemActive : ''}`} onClick={onClick}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

export function MenuSep() {
  return <div className={s.menuSep} role="separator" />;
}

export function MenuNote({ children }: { children: ReactNode }) {
  return <div className={s.menuNote}>{children}</div>;
}
