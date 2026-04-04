from impl_v1.training.data.real_data_curriculum import (
    CurriculumStage,
    RealDataCurriculum,
)


class TestRealDataCurriculum:
    def test_initial_stage_is_baseline_validation(self):
        curriculum = RealDataCurriculum()
        assert curriculum.get_current_stage() == CurriculumStage.BASELINE_VALIDATION
        assert curriculum.get_stage_name() == "Baseline Validation"

    def test_curriculum_advances_from_real_metrics(self):
        curriculum = RealDataCurriculum()

        stage_inputs = [
            (0.82, 0.08, 0.08, 0.40, 3, 600),
            (0.87, 0.04, 0.04, 0.30, 3, 1_000),
            (0.90, 0.03, 0.03, 0.25, 4, 2_000),
            (0.92, 0.02, 0.02, 0.20, 4, 5_000),
            (0.94, 0.01, 0.01, 0.15, 2, 5_000),
            (0.96, 0.01, 0.01, 0.10, 2, 10_000),
        ]

        for accuracy, fpr, fnr, loss, epochs, samples in stage_inputs:
            curriculum.update_metrics(
                accuracy=accuracy,
                fpr=fpr,
                fnr=fnr,
                loss=loss,
                epochs=epochs,
                samples=samples,
            )
            advanced, _ = curriculum.try_advance()
            assert advanced is True

        assert curriculum.state.curriculum_complete is True

    def test_curriculum_rejects_insufficient_real_data(self):
        curriculum = RealDataCurriculum()
        curriculum.update_metrics(
            accuracy=0.95,
            fpr=0.01,
            fnr=0.01,
            loss=0.10,
            epochs=3,
            samples=100,
        )
        advanced, message = curriculum.try_advance()
        assert advanced is False
        assert "Samples" in message
