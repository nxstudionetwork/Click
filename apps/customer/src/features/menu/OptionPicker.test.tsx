import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { Product } from '@click/api';
import { needsChoices, OptionPicker, useOptionSelection } from './OptionPicker';

const pizza = {
  id: 'p1', name: 'Margherita', price: '200.00',
  optionGroups: [
    { id: 'g1', name: 'Size', minSelect: 1, maxSelect: 1, options: [
      { id: 'reg', name: 'Regular', priceDelta: '0.00', isAvailable: true }, { id: 'lg', name: 'Large', priceDelta: '150.00', isAvailable: true }] },
    { id: 'g2', name: 'Extras', minSelect: 0, maxSelect: 2, options: [
      { id: 'ch', name: 'Cheese', priceDelta: '50.00', isAvailable: true }, { id: 'ol', name: 'Olives', priceDelta: '30.00', isAvailable: true },
      { id: 'tr', name: 'Truffle', priceDelta: '90.00', isAvailable: false }] },
  ],
} as unknown as Product;

function Harness() {
  const sel = useOptionSelection(pizza);
  return (
    <>
      <OptionPicker product={pizza} currency="INR" selection={sel} />
      <output aria-label="price">{sel.unitPrice}</output>
      <output aria-label="ids">{sel.optionIds.join(',')}</output>
    </>
  );
}

describe('OptionPicker', () => {
  it('starts required single choices on the first option and previews the price', async () => {
    render(<Harness />);
    expect(needsChoices(pizza)).toBe(true);
    expect(screen.getByRole('radio', { name: /Regular/ })).toBeChecked();
    expect(screen.getByLabelText('price')).toHaveTextContent('200');
    await userEvent.click(screen.getByRole('radio', { name: /Large/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: /Cheese/ }));
    expect(screen.getByLabelText('price')).toHaveTextContent('400');
    expect(screen.getByLabelText('ids')).toHaveTextContent('lg,ch');
  });

  it('enforces the group limit and unavailable options', async () => {
    render(<Harness />);
    expect(screen.getByRole('checkbox', { name: /Truffle/ })).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: /Cheese/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: /Olives/ }));
    expect(screen.getByText('Optional · up to 2')).toBeInTheDocument();
    expect(screen.getByLabelText('price')).toHaveTextContent('280');
  });
});
