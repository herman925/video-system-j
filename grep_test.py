def _fmt_relative(iso_str: str) -> str:
    def _lerp_rgb(s: int):
    def _score_info(score: "Optional[int]"):
        def _span(tip, css, icon, val):
    def _score_html(rating: "Optional[int]") -> str:
    def _svg_score_badge(score: "Optional[int]", size=48) -> str:
        def _beams(col):
        def _particles(col):
        def _god_rays(col):
        def make_spiky_burst(color, outer, inner, points=12):
    def _rebuild_left_list() -> None:
    def _build_actress_row(actress_id: str, actress: dict) -> None:
    def _build_actress_ref_match_row(
    def _select_actress(actress_id: str) -> None:
    def _select_actress_video(actress_id: str, ref: str) -> None:
    def _refresh_right_panel() -> None:
    def _build_empty_right() -> None:
    def _build_actress_inspector(
        def _is_fetched_solo_video(video: dict) -> bool:
                    def _open_score_dialog(
                                def _commit_score(val):
                                def _do_save():
                    def _open_rename_dialog(
                                def _do_rename(rdlg=_rdlg, ninp=_name_inp, a=aid):
    def _build_video_row(
                def _open_cover_zoom(r=ref):
    def _toggle_video_downloaded(
    def _set_filter(actress_id: str, value: str) -> None:
    def _set_star_rating(actress_id: str, value: "Optional[int]") -> None:
    def _set_sort(key: str) -> None:
    def _set_search_mode(mode: str) -> None:
    def _on_video_click(ref: str, actress_id: str) -> None:
    def _do_mark_all_seen(actress_id: str) -> None:
    def _queue_cover_fetch(actress_id: str, *, silent: bool = False) -> None:
        def _notify(msg: str, color: str = "info") -> None:
        def _on_cover_ok(ref: str) -> None:
        def _on_meta(ref: str, meta: dict) -> None:
        def _notify(msg: str, color: str = "info", **kw) -> None:
        def _notify(msg: str, color: str = "info", **kw) -> None:
    def _confirm_delete(actress_id: str) -> None:
                def _do_delete():
    def _open_add_dialog() -> None:
    def _on_save_tracker(cover_w: int, left_panel_w: int = _DEFAULT_LEFT_W) -> None:
                def _on_search(e):