import {LitElement, html, css} from 'lit';
import {customElement, property, state} from 'lit/decorators.js';
import {repeat} from 'lit/directives/repeat.js';
import range from 'lodash-es/range';

import {EventRegistrationMixin} from './event-listener-setup';
import {SearchaliciousEvents} from './enums';
import {SearchResultEvent} from './events';

/**
 * A component to display pagination for search results.
 */
@customElement('searchalicious-pages')
export class SearchaliciousPages extends EventRegistrationMixin(LitElement) {
  static override styles = css`
    ul {
      list-style-type: none;
    }
    li {
      display: inline-block;
      margin: 0 0.5rem;
    }
    .current button {
      font-weight: bold;
    }
  `;

  /**
   * the search we display result for,
   * this corresponds to `name` attribute of corresponding search-bar
   */
  @property({attribute: 'search-name'})
  searchName = 'searchalicious';

  /**
   * Wether or not we should add the jump to first shortcuts
   */
  @property({attribute: 'display-first', type: Boolean})
  displayFirst = true;

  /**
   * Wether or not we should add the jump to end shortcuts
   */
  @property({attribute: 'display-last', type: Boolean})
  displayLast = true;

  /**
   * How many pages should we display as clickable links / buttons
   */
  @property({attribute: 'displayed-pages', type: Number})
  displayedPages = 5;

  /**
   * Do we have an already launched search
   */
  @state()
  searchLaunched = false;

  /**
   * Number of pages in current search
   */
  @state()
  _pageCount?: number;

  /**
   * Current displayed page number
   */
  @state()
  _currentPage?: number;

  /**
   * the first page to be displayed as a number
   */
  @state()
  _startRange?: number;

  /**
   * the last page to be displayed as a number
   */
  @state()
  _endRange?: number;

  /**
   * HTML to display when there are no results
   *
   * Can be overridden by a "no-results" slot
   */
  noResults = html``;

  /**
   * HTML to display before anysearch is launched
   *
   * Can be overridden by a "before-search" slot
   */
  beforeSearch = html``;

  /**
   * Update state on search received
   */
  _updatePages(event: Event) {
    const detail = (event as SearchResultEvent).detail;
    if (detail.searchName === this.searchName) {
      this.searchLaunched = true;
      this._pageCount = detail.pageCount;
      this._currentPage = detail.currentPage;
      [this._startRange, this._endRange] = this._computeRange(
        this._currentPage,
        this._pageCount
      );
      this.requestUpdate();
    }
  }

  /**
   * compute startRange and endRange
   */
  _computeRange(currentPage?: number, pageCount?: number) {
    if (!currentPage || !pageCount) {
      return [undefined, undefined];
    }
    // we try to display one page before
    let start =
      this.displayedPages > 2 ? Math.max(currentPage - 1, 1) : currentPage;
    const end = Math.min(start + this.displayedPages - 1, pageCount);
    if (end - start < this.displayedPages) {
      // near end of the list, show more pages before the end
      start = Math.max(1, end - this.displayedPages + 1);
    }
    return [start, end];
  }

  _isFirstPage() {
    return !!(this._currentPage && this._currentPage === 1);
  }
  _isLastPage() {
    return !!(
      this._currentPage &&
      this._pageCount &&
      this._currentPage >= this._pageCount
    );
  }
  _hasStartEllipsis() {
    return !!(this._startRange && this._startRange > 1);
  }
  _hasEndEllipsis() {
    return !!(
      this._endRange &&
      this._pageCount &&
      this._endRange < this._pageCount
    );
  }
  _displayPages() {
    if (!this._startRange || !this._endRange) {
      return [];
    }
    return range(this._startRange, this._endRange + 1);
  }

  override render() {
    if (this._pageCount) {
      return this.renderPagination();
    } else if (this.searchLaunched) {
      return html`<slot name="no-results">${this.noResults}</slot>`;
    } else {
      return html`<slot name="before-search">${this.beforeSearch}</slot>`;
    }
  }

  /**
   * Render the pagination widget (when we have pages)
   */
  renderPagination() {
    return html`
      <nav part="nav">
        <ul part="pages">
          ${this.displayFirst
            ? html` <li @click=${this._firstPage} part="first">
                <slot name="first"
                  ><button ?disabled=${this._isFirstPage()}>|&lt;</button></slot
                >
              </li>`
            : ''}
          <li @click=${this._prevPage} part="previous">
            <slot name="previous"
              ><button ?disabled=${this._isFirstPage()}>&lt;</button></slot
            >
          </li>
          ${this._hasStartEllipsis()
            ? html` <li part="start-ellipsis">
                <slot name="start-ellipsis">…</slot>
              </li>`
            : ''}
          ${repeat(
            this._displayPages(),
            (page, _) => html` <li
              class="${page === this._currentPage! ? 'current' : ''}"
              part="${page === this._currentPage! ? 'current-' : ''}page"
            >
              <button @click=${() => this._askPageChange(page)}>${page}</button>
            </li>`
          )}
          ${this._hasEndEllipsis()
            ? html` <li part="end-ellipsis">
                <slot name="end-ellipsis">…</slot>
              </li>`
            : ''}
          <li @click=${this._nextPage} part="next">
            <slot name="next"
              ><button ?disabled=${this._isLastPage()}>&gt;</button></slot
            >
          </li>
          ${this.displayLast
            ? html` <li @click=${this._lastPage} part="last">
                <slot name="last"
                  ><button ?disabled=${this._isLastPage()}>&gt;|</button></slot
                >
              </li>`
            : ''}
        </ul>
      </nav>
    `;
  }

  _firstPage() {
    this._askPageChange(1);
  }

  _lastPage() {
    this._askPageChange(this._pageCount!);
  }

  _prevPage() {
    this._askPageChange(Math.max(1, this._currentPage! - 1));
  }

  _nextPage() {
    this._askPageChange(Math.min(this._currentPage! + 1, this._pageCount!));
  }

  /**
   * Request a page change
   */
  _askPageChange(page: number) {
    if (page !== this._currentPage) {
      this.dispatchEvent(
        new CustomEvent(SearchaliciousEvents.CHANGE_PAGE, {
          detail: {
            searchName: this.searchName,
            page: page,
          },
          bubbles: true,
        })
      );
    }
  }

  /**
   * Connect search event handlers.
   */
  override connectedCallback() {
    super.connectedCallback();
    this.addEventHandler(SearchaliciousEvents.NEW_RESULT, (event) =>
      this._updatePages(event)
    );
  }
  // connect to our specific events
  override disconnectedCallback() {
    super.disconnectedCallback();
    this.removeEventHandler(SearchaliciousEvents.NEW_RESULT, (event) =>
      this._updatePages(event)
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'searchalicious-pages': SearchaliciousPages;
  }
}