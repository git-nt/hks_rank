from pathlib import Path
from typing import List, Tuple
import pandas as pd
from loguru import logger
import os
import json 

class QuizRankingGenerator:
    """Generates rankings from quiz scores stored in Excel sheets."""
    
    PLAYER_NAME_MAPPING = {
        'Krešimir Sučević Međeral': 'Krešimir Sučević-Međeral'
    }
    HR_QUIZ_IDENTIFIERS = ["12x7", "Hrvatskih 100"]
    REQUIRED_COLUMNS = ['Player', 'Score']
    
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.excel_data = pd.ExcelFile(file_path)
        self.all_players = pd.DataFrame()
        self.pivoted_data = pd.DataFrame()
        self.quiz_order: List[str] = []
        self.hr_12x7_quizzes: List[str] = []
        self.other_quizzes: List[str] = []

    def process_sheet(self, sheet_name: str) -> None:
        """Process a single sheet from the Excel file.
        
        Args:
            sheet_name: Name of the sheet to process
        """
        sheet_df = self.excel_data.parse(sheet_name, header=None)
        quiz_name = sheet_df.iloc[0, 0]
        max_points = sheet_df.iloc[0, 1]

        if quiz_name not in self.quiz_order:
            self.quiz_order.append(quiz_name)

        players_data = self._prepare_player_data(sheet_df, quiz_name, max_points)
        self.all_players = pd.concat([self.all_players, players_data], ignore_index=True)


    def _prepare_player_data(self, sheet_df: pd.DataFrame, quiz_name: str, max_points: float) -> pd.DataFrame:
        """Prepare player data from a sheet.
        
        Args:
            sheet_df: DataFrame containing the sheet data
            quiz_name: Name of the quiz
            max_points: Maximum points possible for the quiz
        
        Returns:
            DataFrame with processed player data
        """
        players_data = sheet_df.iloc[1:].copy()
        players_data.columns = self.REQUIRED_COLUMNS
        players_data['Player'] = players_data['Player'].replace(self.PLAYER_NAME_MAPPING)
        
        top_score = players_data['Score'].max()
        players_data['Scaled Score'] = (players_data['Score'] / top_score) * max_points
        players_data['Quiz'] = quiz_name
        players_data['Max Points'] = max_points
        
        return players_data
    

    def process_all_sheets(self) -> None:
        """Process all sheets in the Excel file."""
        for sheet_name in self.excel_data.sheet_names:
            self.process_sheet(sheet_name)


    def pivot_scores(self) -> None:
        """Create a pivot table of scores by player and quiz."""
        self.pivoted_data = self.all_players.pivot_table(
            index='Player',
            columns='Quiz',
            values='Scaled Score',
            aggfunc='first'
        ).fillna(0)
        
        self.pivoted_data.columns.name = None
        self.pivoted_data = self.pivoted_data.reset_index()
        self.pivoted_data = self.pivoted_data[['Player'] + self.quiz_order]


    def categorize_quizzes(self) -> None:
        """Categorize quizzes into HR 12x7 and other types."""
        self.hr_12x7_quizzes = [
            quiz for quiz in self.quiz_order 
            if any(identifier in quiz for identifier in self.HR_QUIZ_IDENTIFIERS)
        ]
        self.other_quizzes = [
            quiz for quiz in self.quiz_order 
            if quiz not in self.hr_12x7_quizzes
        ]


    def _calculate_category_score(self, scores: List[float], drop_count: int = 2) -> float:
        """Calculate category score after dropping lowest scores.
        
        Args:
            scores: List of scores to process
            drop_count: Number of lowest scores to drop
        
        Returns:
            Total score after dropping lowest scores
        """
        if len(scores) <= drop_count:
            return sum(scores)
        return sum(sorted(scores, reverse=True)[:-drop_count])


    def calculate_total_scores(self) -> None:
        """Calculate total scores for each player."""
        drop_count = 3  # Change this value to adjust how many other quizzes to drop
        best_combined_12x7_count = 5  # Always take the top 5 scores across 12x7 and Hrvatskih 100 quizzes

        def calculate_partial_scores(row) -> Tuple[float, float, float]:
            # Combine scores from both "12x7" and "Hrvatskih 100" quizzes.
            combined_scores = [row[quiz] for quiz in self.quiz_order if "12x7" in quiz or "Hrvatskih 100" in quiz]
            other_scores = [row[quiz] for quiz in self.other_quizzes if quiz not in combined_scores]
            
            # Calculate all scores.
            best_combined_12x7 = sum(sorted(combined_scores, reverse=True)[:best_combined_12x7_count])
            best_other = self._calculate_category_score(other_scores, drop_count=drop_count)
            total_score = best_combined_12x7 + best_other
            
            return best_combined_12x7, best_other, total_score

        partial_scores = self.pivoted_data.apply(calculate_partial_scores, axis=1)
        
        # Dynamically name the "Other - Best xx" column
        other_best_count = len(self.other_quizzes) - drop_count  # Use the drop_count variable
        other_best_column_name = f'Other - Best {other_best_count}'
        self.pivoted_data[other_best_column_name] = partial_scores.map(lambda x: x[1])
        
        self.pivoted_data['Total Score'] = partial_scores.map(lambda x: x[2])


    def sort_and_reformat(self) -> None:
        """Sort and reformat the final rankings."""
        self.pivoted_data = self.pivoted_data.sort_values(
            by='Total Score', 
            ascending=False
        ).reset_index(drop=True)
        self.pivoted_data.index = range(1, len(self.pivoted_data) + 1)

        # Define the first columns in specific order
        fixed_columns = ['Player', 'Total Score']
        
        # Get remaining columns
        quiz_columns = [col for col in self.quiz_order if col not in fixed_columns]
        twelve_x7_columns = [col for col in quiz_columns if "12x7" in col]
        hrvatskih_100_column = [col for col in quiz_columns if "Hrvatskih 100" in col]
        non_twelve_x7_columns = [col for col in quiz_columns if "12x7" not in col and "Hrvatskih 100" not in col]
        
        # Combine all columns in desired order, placing 12x7 columns and "Hrvatskih 100" first
        reordered_columns = (
            fixed_columns +
            twelve_x7_columns +  # Place all 12x7 columns before others
            hrvatskih_100_column +  # Place "Hrvatskih 100" immediately after 12x7 columns
            non_twelve_x7_columns
        )

        self.pivoted_data = self.pivoted_data[reordered_columns]


    def run(self) -> pd.DataFrame:
        """Execute the complete ranking generation process.
        
        Returns:
            DataFrame containing the final rankings
        """
        self.process_all_sheets()
        self.pivot_scores()
        self.categorize_quizzes()
        self.calculate_total_scores()
        self.sort_and_reformat()
        return self.pivoted_data


def main() -> None:
    """Main entry point for the ranking generator."""
    try:
        file_path = Path(__file__).parent / 'hks_scores.xlsx'
        ranking = QuizRankingGenerator(file_path)
        final_scores = ranking.run()
        logger.info(final_scores)
        
        output_path = file_path.parent / 'ranking.xlsx'
        final_scores.to_excel(output_path, index=False)
        logger.info(f"Rankings saved to {output_path}")
        logger.info(final_scores.columns)
        # ✅ NEW: Save rankings as JSON for GitHub Pages
        json_output_path = file_path.parent / 'rankings.json'
        final_scores = final_scores.reset_index(names="Rank")
        final_scores = final_scores[["Rank"] + [col for col in final_scores.columns if col != "Rank"]]
        for col in final_scores.select_dtypes(include=['float64', 'int64']).columns:
            if col == "Rank":
                final_scores[col] = final_scores[col].astype(int)
            else:
                final_scores[col] = final_scores[col].apply(lambda x: f"{x:.2f}") 

        final_scores.to_json("rankings.json", orient="records", indent=4, force_ascii=False)
        logger.info(f"Rankings saved to {json_output_path}")
        
    except FileNotFoundError:
        logger.error(f"Input file not found: {file_path}")
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()