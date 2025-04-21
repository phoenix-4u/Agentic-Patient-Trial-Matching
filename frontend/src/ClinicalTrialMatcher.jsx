import React, { useState } from 'react';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Link from '@mui/material/Link';
import SearchIcon from '@mui/icons-material/Search';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import LocationOnIcon from '@mui/icons-material/LocationOn'; // Example icon
import ContactPhoneIcon from '@mui/icons-material/ContactPhone'; // Example icon

// Use Vite's way to get environment variables
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function ClinicalTrialMatcher() {
  const [patientId, setPatientId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState(null); // Store array of matches
  const [error, setError] = useState(null); // Store error message string
  const [message, setMessage] = useState(null); // Store 'no matches' message

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!patientId.trim()) {
      setError('Please enter a Patient ID.');
      setResults(null);
      setMessage(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    setResults(null);
    setMessage(null);
    console.log('Fetching from:', API_URL); // Keep this for debugging

    try {
      const response = await fetch(`${API_URL}/api/v1/trials/find`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patientId: patientId.trim() }),
      });

      if (!response.ok) {
        let errorDetail = `Request failed! Status: ${response.status}`;
        try {
          const errorData = await response.json();
          errorDetail = errorData.detail || errorDetail;
        } catch (parseError) { /* Ignore */ }
        throw new Error(errorDetail);
      }

      const data = await response.json();

      if (data.status === 'success') {
        setResults(data.matches);
        if (data.matches.length === 0) {
          setMessage('Search successful, but no trials matched the criteria.');
        }
      } else if (data.status === 'no_matches_found') {
        setMessage(data.message || 'No suitable recruiting trials found.');
        setResults([]);
      } else {
        throw new Error(data.message || 'Received an unexpected status from server.');
      }
    } catch (err) {
      console.error("API call failed:", err);
      setError(err.message || 'Failed to fetch trial data. Check connection or contact support.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box sx={{ my: 2 }}> {/* Add some vertical margin */}
      <Typography variant="h5" component="h2" gutterBottom>
        Find Clinical Trials
      </Typography>
      <Box
        component="form"
        onSubmit={handleSubmit}
        sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 3 }} // Use gap for spacing
      >
        <TextField
          label="Patient ID"
          variant="outlined"
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
          disabled={isLoading}
          fullWidth // Take available width
          size="small" // Slightly smaller input
          placeholder="e.g., PATIENT_001"
        />
        <Button
          type="submit"
          variant="contained"
          disabled={isLoading}
          startIcon={isLoading ? <CircularProgress size={20} color="inherit" /> : <SearchIcon />}
          sx={{ minWidth: 120 }} // Ensure button doesn't shrink too much
        >
          {isLoading ? 'Searching...' : 'Search'}
        </Button>
      </Box>

      {/* --- Status Messages --- */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {message && (
         <Alert severity="info" sx={{ mb: 2 }}>
          {message}
        </Alert>
      )}
      {isLoading && !error && !message && ( // Show spinner only when actively loading initial results
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
            <CircularProgress />
        </Box>
      )}


      {/* --- Results --- */}
      {results && results.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" component="h3" gutterBottom>
            Potential Matches:
          </Typography>
          <List sx={{ p: 0 }}> {/* Remove default padding */}
            {results.map((trial) => (
              <Card key={trial.trialId} sx={{ mb: 2 }} variant="outlined">
                <CardContent>
                  <Typography variant="h6" component="div" gutterBottom>
                    {trial.title} ({trial.trialId})
                  </Typography>

                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                     <Chip label={trial.status} color={trial.status === 'Recruiting' ? 'success' : 'default'} size="small" />
                     <Chip label={`Phase: ${trial.phase}`} variant="outlined" size="small" />
                     <Chip label={`Condition: ${trial.condition}`} variant="outlined" size="small" />
                  </Box>

                  {trial.locations && trial.locations.length > 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                        <LocationOnIcon fontSize="small" /> Locations: {trial.locations.join(', ')}
                    </Typography>
                  )}
                  {trial.contactInfo && (
                     <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                         <ContactPhoneIcon fontSize="small" /> Contact: {trial.contactInfo}
                     </Typography>
                  )}
                   {trial.detailsUrl && (
                    <Typography variant="body2" sx={{ mb: 2 }}>
                        <Link href={trial.detailsUrl} target="_blank" rel="noopener noreferrer" underline="hover">
                            View Full Details on Registry
                        </Link>
                    </Typography>
                 )}

                  {trial.matchRationale && trial.matchRationale.length > 0 && (
                    <Box sx={{ mb: 1 }}>
                        <Typography variant="subtitle2">Match Rationale:</Typography>
                        <List dense disablePadding>
                            {trial.matchRationale.map((reason, index) => (
                            <ListItem key={`rationale-${index}`} disableGutters sx={{py: 0.2}}>
                                <ListItemIcon sx={{ minWidth: 32 }}>
                                    <CheckCircleOutlineIcon color="success" fontSize="small" />
                                </ListItemIcon>
                                <ListItemText primary={reason} primaryTypographyProps={{ variant: 'body2' }} />
                            </ListItem>
                            ))}
                        </List>
                    </Box>
                  )}

                  {trial.flags && trial.flags.length > 0 && (
                     <Box>
                        <Typography variant="subtitle2">Flags / Potential Issues:</Typography>
                         <List dense disablePadding>
                            {trial.flags.map((flag, index) => (
                            <ListItem key={`flag-${index}`} disableGutters sx={{py: 0.2}}>
                                <ListItemIcon sx={{ minWidth: 32 }}>
                                    <WarningAmberIcon color="warning" fontSize="small" />
                                </ListItemIcon>
                                <ListItemText primary={flag} primaryTypographyProps={{ variant: 'body2' }} />
                            </ListItem>
                            ))}
                        </List>
                    </Box>
                  )}

                </CardContent>
              </Card>
            ))}
          </List>
        </Box>
      )}
    </Box>
  );
}

export default ClinicalTrialMatcher;